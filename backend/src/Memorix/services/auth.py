"""Password hashing, single-use guardian invitations and revocable sessions."""

import argparse
import getpass
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..entities.study import LoginLimit, LoginSession, MinorInvitation, User


def now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=5)
    return f"scrypt$16384$5${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, parallelism, salt, digest = encoded.split("$")
        if algorithm != "scrypt" or rounds != "16384" or parallelism != "5":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=5)
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(session: Session, admin: User, minor_email: str) -> str:
    token = secrets.token_urlsafe(32)
    session.add(MinorInvitation(token_hash=token_hash(token), minor_email=minor_email.strip().lower(),
                                verified_by_id=admin.id, verified_at=now(),
                                expires_at=now() + timedelta(days=2)))
    session.commit()
    return token


def register_student(session: Session, email: str, password: str, *, adult_confirmed: bool,
                     invitation_token: str | None = None) -> User | None:
    invitation = None
    if not adult_confirmed:
        if not invitation_token:
            return None
        invitation = session.scalar(select(MinorInvitation).where(
            MinorInvitation.token_hash == token_hash(invitation_token),
            MinorInvitation.minor_email == email.strip().lower(),
            MinorInvitation.claimed_at.is_(None), MinorInvitation.expires_at > now(),
        ).with_for_update())
        if invitation is None:
            return None
    user = User(email=email.strip().lower(), password_hash=hash_password(password),
                role="student", adult_confirmed=adult_confirmed)
    session.add(user)
    session.flush()
    if invitation is not None:
        invitation.claimed_by_id = user.id
        invitation.claimed_at = now()
    session.commit()
    return user


def check_login(session: Session, email: str, password: str) -> tuple[User | None, bool]:
    """Persist a short, account-keyed guess budget across API workers."""
    normalized = email.strip().lower()
    key = token_hash(normalized)
    session.execute(insert(LoginLimit).values(key_hash=key, failures=0,
                    expires_at=now() + timedelta(minutes=15)).on_conflict_do_nothing())
    limit = session.scalar(select(LoginLimit).where(LoginLimit.key_hash == key).with_for_update())
    current = now()
    if limit.expires_at <= current:
        limit.failures = 0
        limit.expires_at = current + timedelta(minutes=15)
    if limit.failures >= 5:
        session.commit()
        return None, True
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None or not verify_password(password, user.password_hash):
        limit.failures += 1
        session.commit()
        return None, False
    limit.failures = 0
    session.commit()
    return user, False


def start_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(LoginSession(user_id=user.id, token_hash=token_hash(token),
                             expires_at=now() + timedelta(days=7)))
    session.commit()
    return token


def get_active_session(session: Session, token: str) -> tuple[User, LoginSession] | None:
    return session.execute(select(User, LoginSession).join(LoginSession, LoginSession.user_id == User.id).where(
        LoginSession.token_hash == token_hash(token), LoginSession.revoked_at.is_(None),
        LoginSession.expires_at > now(),
    )).first()


def create_admin(email: str, password: str, session: Session) -> None:
    session.add(User(email=email.strip().lower(), password_hash=hash_password(password),
                     role="admin", adult_confirmed=True))
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a local Memorix administrator")
    parser.add_argument("command", choices=["create-admin"])
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass.getpass("Senha do admin (mín. 12 caracteres): ")
    if len(password) < 12 or len(password) > 256 or "@" not in args.email:
        parser.error("e-mail ou senha inválidos")
    from ..providers.database import SessionLocal
    with SessionLocal() as session:
        create_admin(args.email, password, session)
    print("Administrador criado")


if __name__ == "__main__":
    main()
