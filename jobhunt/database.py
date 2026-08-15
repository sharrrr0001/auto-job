"""Persistent web-dashboard storage and password/session primitives.

SQLite is used for local development.  Production deployments use the
``DATABASE_URL`` supplied by a serverless Postgres provider such as Neon.
The dashboard deliberately refuses to fall back to Vercel's ephemeral
filesystem: appearing to save data and then losing it on the next cold start
would be worse than an actionable configuration error.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


PASSWORD_ITERATIONS = 600_000
SESSION_DAYS = 7
DATA_FIELDS = {"profile", "settings", "companies", "applications", "run"}


class StorageNotConfigured(RuntimeError):
    """Raised when a production deployment has no persistent database."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join((
        "pbkdf2_sha256",
        str(PASSWORD_ITERATIONS),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    ))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Database:
    """Small SQL repository supporting both SQLite and Postgres."""

    def __init__(self, root: Path):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            self.kind = "postgres"
            self.target = database_url
        else:
            if os.getenv("VERCEL"):
                raise StorageNotConfigured(
                    "Persistent storage is not configured. Add a Neon Postgres "
                    "DATABASE_URL to the Vercel project and redeploy."
                )
            self.kind = "sqlite"
            configured = os.getenv("JOBHUNT_DB_PATH", "").strip()
            self.target = str(Path(configured) if configured else root / "jobhunt.sqlite3")
        self._schema_lock = threading.Lock()
        self._schema_ready = False
        self.ensure_schema()

    def _sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.kind == "postgres" else statement

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.kind == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - packaging error
                raise StorageNotConfigured(
                    "Postgres support is unavailable. Install psycopg[binary]."
                ) from exc
            connection = psycopg.connect(self.target, row_factory=dict_row)
        else:
            path = Path(self.target)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=20)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._schema_lock:
            if self._schema_ready:
                return
            statements = [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS user_data (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    profile_json TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    companies_json TEXT NOT NULL,
                    applications_json TEXT NOT NULL,
                    run_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            ]
            with self.connection() as connection:
                for statement in statements:
                    connection.execute(statement)
            self._schema_ready = True

    @staticmethod
    def _row(row: Any) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    @staticmethod
    def public_user(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "role": row["role"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
        }

    def user_count(self) -> int:
        with self.connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(dict(row)["count"])

    def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str,
        role: str,
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        user_id = str(uuid.uuid4())
        timestamp = _now()
        with self.connection() as connection:
            connection.execute(
                self._sql(
                    "INSERT INTO users "
                    "(id, email, name, password_hash, role, active, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (user_id, email.casefold(), name, hash_password(password), role, 1, timestamp, timestamp),
            )
            connection.execute(
                self._sql(
                    "INSERT INTO user_data "
                    "(user_id, profile_json, settings_json, companies_json, "
                    "applications_json, run_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    user_id,
                    json.dumps(defaults["profile"], ensure_ascii=False),
                    json.dumps(defaults["settings"], ensure_ascii=False),
                    json.dumps(defaults["companies"], ensure_ascii=False),
                    json.dumps(defaults["applications"], ensure_ascii=False),
                    json.dumps(defaults["run"], ensure_ascii=False),
                    timestamp,
                ),
            )
        return self.get_user(user_id) or {}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM users WHERE id = ?"), (user_id,)
            ).fetchone()
        return self._row(row)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM users WHERE email = ?"), (email.casefold(),)
            ).fetchone()
        return self._row(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY created_at ASC"
            ).fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            summary = self.public_user(row)
            data = self.get_user_data(row["id"])
            applications = data.get("applications", {})
            summary["data"] = {
                "tracked": len(applications),
                "applied": sum(1 for item in applications.values() if item.get("applied")),
                "companies": len(data.get("companies", [])),
                "last_run": data.get("run", {}).get("finished_at"),
            }
            result.append(summary)
        return result

    def update_user(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"email", "name", "role", "active"}
        assignments: list[str] = []
        values: list[Any] = []
        for key in allowed:
            if key in changes and changes[key] is not None:
                assignments.append(f"{key} = ?")
                value = changes[key]
                if key == "email":
                    value = str(value).casefold()
                if key == "active":
                    value = 1 if value else 0
                values.append(value)
        if changes.get("password"):
            assignments.append("password_hash = ?")
            values.append(hash_password(str(changes["password"])))
        if not assignments:
            return self.get_user(user_id)
        assignments.append("updated_at = ?")
        values.extend((_now(), user_id))
        with self.connection() as connection:
            connection.execute(
                self._sql(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?"),
                tuple(values),
            )
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        with self.connection() as connection:
            cursor = connection.execute(
                self._sql("DELETE FROM users WHERE id = ?"), (user_id,)
            )
        return bool(cursor.rowcount)

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        with self.connection() as connection:
            connection.execute(
                self._sql(
                    "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) "
                    "VALUES (?, ?, ?, ?)"
                ),
                (session_hash(token), user_id, expires_at.isoformat(timespec="seconds"), _now()),
            )
        return token

    def user_for_session(self, token: str) -> dict[str, Any] | None:
        digest = session_hash(token)
        timestamp = _now()
        with self.connection() as connection:
            connection.execute(
                self._sql("DELETE FROM sessions WHERE expires_at <= ?"), (timestamp,)
            )
            row = connection.execute(
                self._sql(
                    "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
                    "WHERE sessions.token_hash = ? AND sessions.expires_at > ?"
                ),
                (digest, timestamp),
            ).fetchone()
        user = self._row(row)
        return user if user and bool(user["active"]) else None

    def delete_session(self, token: str) -> None:
        with self.connection() as connection:
            connection.execute(
                self._sql("DELETE FROM sessions WHERE token_hash = ?"),
                (session_hash(token),),
            )

    def delete_user_sessions(self, user_id: str) -> None:
        with self.connection() as connection:
            connection.execute(
                self._sql("DELETE FROM sessions WHERE user_id = ?"), (user_id,)
            )

    def get_user_data(self, user_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM user_data WHERE user_id = ?"), (user_id,)
            ).fetchone()
        if row is None:
            return {}
        values = dict(row)
        return {
            "profile": json.loads(values["profile_json"]),
            "settings": json.loads(values["settings_json"]),
            "companies": json.loads(values["companies_json"]),
            "applications": json.loads(values["applications_json"]),
            "run": json.loads(values["run_json"]),
        }

    def update_user_data(self, user_id: str, field: str, value: Any) -> None:
        if field not in DATA_FIELDS:
            raise ValueError(f"Unknown data field: {field}")
        column = f"{field}_json"
        with self.connection() as connection:
            connection.execute(
                self._sql(
                    f"UPDATE user_data SET {column} = ?, updated_at = ? WHERE user_id = ?"
                ),
                (json.dumps(value, ensure_ascii=False), _now(), user_id),
            )

    def reset_user_data(self, user_id: str, defaults: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                self._sql(
                    "UPDATE user_data SET profile_json = ?, settings_json = ?, "
                    "companies_json = ?, applications_json = ?, run_json = ?, "
                    "updated_at = ? WHERE user_id = ?"
                ),
                (
                    json.dumps(defaults["profile"], ensure_ascii=False),
                    json.dumps(defaults["settings"], ensure_ascii=False),
                    json.dumps(defaults["companies"], ensure_ascii=False),
                    json.dumps(defaults["applications"], ensure_ascii=False),
                    json.dumps(defaults["run"], ensure_ascii=False),
                    _now(),
                    user_id,
                ),
            )
