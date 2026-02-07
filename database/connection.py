"""SQLite database connection with WAL mode and context management."""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger("stock_model.database")


class DatabaseConnection:
    """Manages SQLite connections with WAL mode for concurrent reads."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with WAL mode and foreign keys."""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def connect(self):
        """Context manager yielding a database connection with auto-commit."""
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> list:
        """Execute a query and return all results."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def execute_one(self, sql: str, params: tuple = ()):
        """Execute a query and return the first result."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        """Execute an INSERT and return the last row ID."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid

    def execute_many(self, sql: str, param_list: list):
        """Execute a parameterized query for each set of params."""
        with self.connect() as conn:
            conn.executemany(sql, param_list)


_db: DatabaseConnection | None = None


def get_connection(db_path: Path | None = None) -> DatabaseConnection:
    """Get or create the singleton database connection."""
    global _db
    if _db is None:
        if db_path is None:
            from config.settings import get_settings
            db_path = get_settings().db_path
        _db = DatabaseConnection(db_path)
    return _db
