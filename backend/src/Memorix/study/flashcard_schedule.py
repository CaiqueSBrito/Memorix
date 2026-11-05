"""Política de caixas explícita; não estima retenção nem corrige texto livre."""

from datetime import datetime, timedelta, timezone


RATINGS = ("again", "hard", "good", "easy")
BOX_INTERVAL_DAYS = (1, 3, 7, 14, 30, 60)


def utc_instant(value: datetime | None = None) -> datetime:
    """Normaliza um instante com fuso; None usa o relógio UTC do processo."""
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Informe um instante com fuso horário.")
    return value.astimezone(timezone.utc)


def schedule_review(box: int, rating: str, reviewed_at: datetime) -> dict:
    """Retorna caixa e vencimento a partir da autoavaliação informada.

    again: caixa 0 e dez minutos. hard: recua uma caixa, mínimo 1.
    good: avança uma caixa. easy: avança duas. As caixas 1–6 têm
    intervalos de 1, 3, 7, 14, 30 e 60 dias, respectivamente.
    """
    if type(box) is not int or not 0 <= box <= len(BOX_INTERVAL_DAYS):
        raise ValueError("A caixa deve ser um inteiro entre 0 e 6.")
    if rating not in RATINGS:
        raise ValueError("Autoavaliação não suportada.")
    if not isinstance(reviewed_at, datetime):
        raise ValueError("Informe o instante da revisão com fuso horário.")
    instant = utc_instant(reviewed_at)
    if rating == "again":
        next_box = 0
        interval = timedelta(minutes=10)
    else:
        if rating == "hard":
            next_box = max(1, box - 1)
        else:
            next_box = min(len(BOX_INTERVAL_DAYS), box + (2 if rating == "easy" else 1))
        interval = timedelta(days=BOX_INTERVAL_DAYS[next_box - 1])
    try:
        due_at = instant + interval
    except OverflowError:
        raise ValueError("A próxima revisão excede o intervalo de datas suportado.") from None
    return {"box": next_box, "due_at": due_at.isoformat()}
