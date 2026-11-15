"""
METLINK PostgreSQL Connection Module (Psycopg 3).

Responsibilities:
- Load database configuration from environment variables (or .env file).
- Create connections to PostgreSQL using Psycopg 3.
- Provide reusable connection and transaction context managers.
- Commit successful operations and roll back failed operations automatically.
- Close connections reliably and handle connection failures safely.
- Provide a simple connection health check.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


def _load_dotenv_if_present(env_path: Optional[Path] = None) -> None:
    """Load key=value pairs from a local .env file without overriding existing env vars."""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def get_db_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build PostgreSQL connection parameters from environment variables.

    Supported environment variables:
    - DB_HOST (default: localhost)
    - DB_PORT (default: 5432)
    - DB_NAME (default: metlink_db)
    - DB_USER (default: metlink_user)
    - DB_PASSWORD (required for authenticated connections)
    - DB_CONNECT_TIMEOUT (default: 5)
    """
    _load_dotenv_if_present()

    port_raw = os.getenv("DB_PORT", "5432")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid DB_PORT value: {port_raw!r}") from exc

    config: Dict[str, Any] = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": port,
        "dbname": os.getenv("DB_NAME", "metlink_db"),
        "user": os.getenv("DB_USER", "metlink_user"),
        "password": os.getenv("DB_PASSWORD", ""),
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5")),
        "row_factory": dict_row,
    }

    if overrides:
        config.update(overrides)

    return config


def create_connection(overrides: Optional[Dict[str, Any]] = None) -> psycopg.Connection[Dict[str, Any]]:
    """
    Create and return a new Psycopg 3 PostgreSQL connection.
    Raises psycopg.OperationalError if the connection cannot be established.
    """
    config = get_db_config(overrides=overrides)
    try:
        return psycopg.connect(**config)
    except psycopg.Error as exc:
        logger.error(
            "Failed to connect to PostgreSQL database '%s' at %s:%s as user '%s': %s",
            config.get("dbname"),
            config.get("host"),
            config.get("port"),
            config.get("user"),
            exc,
        )
        raise


@contextmanager
def get_connection(
    overrides: Optional[Dict[str, Any]] = None,
) -> Generator[psycopg.Connection[Dict[str, Any]], None, None]:
    """
    Context manager that opens a PostgreSQL connection, commits on normal exit,
    rolls back on any exception, and always closes the connection.
    """
    conn: Optional[psycopg.Connection[Dict[str, Any]]] = None
    try:
        conn = create_connection(overrides=overrides)
        yield conn
        conn.commit()
    except Exception:
        if conn is not None and not conn.closed:
            try:
                conn.rollback()
            except psycopg.Error as rollback_err:
                logger.error("Failed to roll back transaction: %s", rollback_err)
        raise
    finally:
        if conn is not None and not conn.closed:
            conn.close()


@contextmanager
def get_cursor(
    overrides: Optional[Dict[str, Any]] = None,
) -> Generator[psycopg.Cursor[Dict[str, Any]], None, None]:
    """
    Convenience context manager yielding a dict_row cursor inside a managed transaction.
    Commits on success, rolls back on exception, and closes both cursor and connection.
    """
    with get_connection(overrides=overrides) as conn:
        with conn.cursor() as cur:
            yield cur


def check_connection_health(overrides: Optional[Dict[str, Any]] = None) -> bool:
    """
    Execute a lightweight parameterized query ('SELECT %s AS ping') to verify
    database connectivity. Returns True when healthy, False otherwise.
    """
    try:
        with get_cursor(overrides=overrides) as cur:
            cur.execute("SELECT %s AS ping;", (1,))
            row = cur.fetchone()
            return bool(row and row.get("ping") == 1)
    except psycopg.Error as exc:
        logger.warning("Database health check failed: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    healthy = check_connection_health()
    if healthy:
        logger.info("PostgreSQL connection health check PASSED.")
    else:
        logger.error("PostgreSQL connection health check FAILED.")
        raise SystemExit(1)