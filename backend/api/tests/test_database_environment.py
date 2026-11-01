"""Selecionar banco de desenvolvimento sem sobrescrever o .env de produção."""

import json
import os
import subprocess
import sys


def test_environment_file_selects_local_database_without_overriding_process(tmp_path):
    env_file = tmp_path / "local.env"
    env_file.write_text(
        "DB_HOST=127.0.0.1\nDB_PORT=55432\nDB_USER=local_user\n"
        "DB_PASSWORD=local_password\nDB_DATABASE=local_database\nDB_SSLMODE=disable\n",
        encoding="utf-8",
    )
    child_env = {key: value for key, value in os.environ.items() if not key.startswith("DB_")}
    child_env.update(MEMORIX_ENV_FILE=str(env_file), DB_PORT="55433")
    result = subprocess.run(
        [sys.executable, "-c", (
            "import json; from backend.src.Memorix.providers.database import DATABASE_URL; "
            "print(json.dumps({'host': DATABASE_URL.host, 'port': DATABASE_URL.port, "
            "'user': DATABASE_URL.username, 'database': DATABASE_URL.database, "
            "'sslmode': DATABASE_URL.query['sslmode']}))"
        )],
        env=child_env, capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == {
        "host": "127.0.0.1", "port": 55433, "user": "local_user",
        "database": "local_database", "sslmode": "disable",
    }
