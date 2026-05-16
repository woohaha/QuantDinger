"""SQLite DAO for watchlist + auth_cache + telegraph_account + telegraph_pages.

Sync stdlib sqlite3; bot is single-process and storage calls are fast.
Wrap in `asyncio.to_thread` from async handlers if blocking matters.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sqlite3


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    added_by    INTEGER NOT NULL,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_cache (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    token     TEXT NOT NULL,
    saved_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegraph_account (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    short_name   TEXT,
    author_name  TEXT,
    author_url   TEXT,
    auth_url     TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegraph_pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE,
    url        TEXT NOT NULL,
    title      TEXT,
    timeframe  TEXT,
    decision   TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegraph_pages_code_time
    ON telegraph_pages(code, created_at DESC, id DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # ---- watchlist ----
    def watchlist_add(self, code: str, name: str | None, added_by: int) -> None:
        # COALESCE keeps the old name if already set; new non-null name backfills NULL.
        # added_by / added_at stay from the original insert.
        with self._conn:
            self._conn.execute(
                "INSERT INTO watchlist(code, name, added_by, added_at) VALUES (?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name = COALESCE(watchlist.name, excluded.name)",
                (code, name, added_by, _now_iso()),
            )

    def watchlist_remove(self, code: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
            return cur.rowcount > 0

    def watchlist_set_name(self, code: str, name: str | None) -> bool:
        """Force-update name on an existing row. Returns True if a row was updated.

        Unlike watchlist_add, this overwrites unconditionally — caller decides
        whether to call it (e.g. /refresh only calls for rows whose name is NULL).
        """
        with self._conn:
            cur = self._conn.execute(
                "UPDATE watchlist SET name = ? WHERE code = ?", (name, code),
            )
            return cur.rowcount > 0

    def watchlist_list(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT code, name, added_by, added_at FROM watchlist ORDER BY added_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- auth cache ----
    def auth_cache_get(self) -> Optional[str]:
        row = self._conn.execute("SELECT token FROM auth_cache WHERE id = 1").fetchone()
        return row["token"] if row else None

    def auth_cache_set(self, token: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO auth_cache(id, token, saved_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET token = excluded.token, saved_at = excluded.saved_at",
                (token, _now_iso()),
            )

    # ---- telegraph account ----
    def telegraph_account_get(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT access_token, short_name, author_name, author_url, auth_url, created_at "
            "FROM telegraph_account WHERE id = 1"
        ).fetchone()
        return dict(row) if row else None

    def telegraph_account_set(self, *, access_token: str, short_name: str | None,
                              author_name: str | None, author_url: str | None,
                              auth_url: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO telegraph_account(id, access_token, short_name, author_name, "
                "author_url, auth_url, created_at) VALUES (1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token, "
                "short_name = excluded.short_name, author_name = excluded.author_name, "
                "author_url = excluded.author_url, auth_url = excluded.auth_url",
                (access_token, short_name, author_name, author_url, auth_url, _now_iso()),
            )

    # ---- telegraph pages ----
    def telegraph_page_add(self, *, code: str, path: str, url: str,
                           title: str | None, timeframe: str | None,
                           decision: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO telegraph_pages(code, path, url, title, timeframe, decision, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, path, url, title, timeframe, decision, _now_iso()),
            )

    def telegraph_page_latest(self, code: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT code, path, url, title, timeframe, decision, created_at "
            "FROM telegraph_pages WHERE code = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (code,),
        ).fetchone()
        return dict(row) if row else None
