"""SQLite access. One short-lived connection per call keeps background threads independent;
WAL mode lets the app read while a sync or plan generation writes."""
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from core.config import get_settings

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect() -> sqlite3.Connection:
    path = get_settings().database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit, multi-statement writes use transaction()
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def query(sql: str, params: Iterable = ()) -> list[dict]:
    with closing(connect()) as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params))]


def query_one(sql: str, params: Iterable = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable = ()) -> int:
    """Runs one write and returns the number of changed rows."""
    with closing(connect()) as conn:
        return conn.execute(sql, tuple(params)).rowcount


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """All writes inside commit together or not at all."""
    with closing(connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def migrate() -> None:
    """Applies migrations/NNN_*.sql in order; PRAGMA user_version stores the last one applied."""
    with closing(connect()) as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        # Off while migrating: rebuilding a table (drop and rename) would otherwise cascade-delete
        # the rows that reference it. Checked again before each migration is committed.
        conn.execute("PRAGMA foreign_keys = OFF")
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(file.name.split("_", 1)[0])
            if version <= current:
                continue
            log.info("Applying migration %s", file.name)
            conn.executescript(f"BEGIN; {file.read_text(encoding='utf-8')}\nPRAGMA user_version = {version};")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                conn.execute("ROLLBACK")
                raise RuntimeError(f"Migration {file.name} breaks foreign keys")
            conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys = ON")
