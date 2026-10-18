"""SQLite persistence: workers, check-ins, escalations, callback requests, lookups."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
    id INTEGER PRIMARY KEY,
    phone TEXT UNIQUE NOT NULL,
    lang TEXT NOT NULL,
    country TEXT,
    family_phone TEXT,
    created_at TEXT NOT NULL,
    last_checkin_at TEXT,
    last_call_at TEXT,
    missed INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    at TEXT NOT NULL,
    paid INTEGER, passport INTEGER, safe INTEGER
);
CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS callbacks (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL,
    lang TEXT NOT NULL,
    topic TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS lookups (
    id INTEGER PRIMARY KEY,
    phone TEXT,
    query TEXT NOT NULL,
    matched_name TEXT,
    status TEXT,
    score REAL,
    at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def _exec(self, sql: str, args=()) -> sqlite3.Cursor:
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur

    def rows(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args)]

    # Workers
    def upsert_worker(self, phone: str, lang: str, country: str, family_phone: str) -> int:
        self._exec(
            """INSERT INTO workers (phone, lang, country, family_phone, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(phone) DO UPDATE SET lang=excluded.lang, country=excluded.country,
                   family_phone=excluded.family_phone, active=1""",
            (phone, lang, country, family_phone, now()),
        )
        return self.worker_by_phone(phone)["id"]

    def worker(self, worker_id: int) -> dict | None:
        r = self.rows("SELECT * FROM workers WHERE id = ?", (worker_id,))
        return r[0] if r else None

    def worker_by_phone(self, phone: str) -> dict | None:
        r = self.rows("SELECT * FROM workers WHERE phone = ?", (phone,))
        return r[0] if r else None

    def due_workers(self, before_iso: str) -> list[dict]:
        return self.rows(
            "SELECT * FROM workers WHERE active = 1 AND (last_call_at IS NULL OR last_call_at < ?)",
            (before_iso,),
        )

    def mark_called(self, worker_id: int) -> None:
        self._exec("UPDATE workers SET last_call_at = ? WHERE id = ?", (now(), worker_id))

    def record_missed(self, worker_id: int) -> int:
        self._exec("UPDATE workers SET missed = missed + 1 WHERE id = ?", (worker_id,))
        return self.worker(worker_id)["missed"]

    def record_checkin(self, worker_id: int, paid: bool, passport: bool, safe: bool) -> None:
        self._exec(
            "INSERT INTO checkins (worker_id, at, paid, passport, safe) VALUES (?, ?, ?, ?, ?)",
            (worker_id, now(), paid, passport, safe),
        )
        self._exec("UPDATE workers SET missed = 0, last_checkin_at = ? WHERE id = ?", (now(), worker_id))

    # Escalations, callbacks, lookups
    def add_escalation(self, worker_id: int, reason: str) -> int:
        return self._exec(
            "INSERT INTO escalations (worker_id, reason, created_at) VALUES (?, ?, ?)",
            (worker_id, reason, now()),
        ).lastrowid

    def open_escalations(self) -> list[dict]:
        return self.rows(
            """SELECT e.*, w.phone, w.family_phone, w.country, w.lang FROM escalations e
               JOIN workers w ON w.id = e.worker_id WHERE e.status = 'open' ORDER BY e.id DESC"""
        )

    def add_callback(self, phone: str, lang: str, topic: str) -> int:
        return self._exec(
            "INSERT INTO callbacks (phone, lang, topic, created_at) VALUES (?, ?, ?, ?)",
            (phone, lang, topic, now()),
        ).lastrowid

    def open_callbacks(self) -> list[dict]:
        return self.rows("SELECT * FROM callbacks WHERE status = 'open' ORDER BY id DESC")

    def log_lookup(self, phone: str, query: str, matched_name: str | None, status: str | None, score: float) -> None:
        self._exec(
            "INSERT INTO lookups (phone, query, matched_name, status, score, at) VALUES (?, ?, ?, ?, ?, ?)",
            (phone, query, matched_name, status, score, now()),
        )

    def recent_lookups(self, limit: int = 100) -> list[dict]:
        return self.rows("SELECT * FROM lookups ORDER BY id DESC LIMIT ?", (limit,))
