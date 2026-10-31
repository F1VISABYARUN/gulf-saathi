"""Storage for worker cases, calls, check-ins and escalations.

SupabaseStore talks to Supabase's REST API with the server-side secret key.
MemoryStore keeps rows in dicts, for tests and for running locally without
Supabase. Both offer the same five calls: get, select, insert, update, upsert.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

TABLES = ("workers", "calls", "checkins", "escalations", "contact_reports", "scam_alerts")
# Tables whose primary key the database generates (calls use Bolna's execution id).
GENERATED_IDS = {"workers", "checkins", "escalations", "contact_reports", "scam_alerts"}


class StoreError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self.tables: dict[str, list[dict]] = {t: [] for t in TABLES}

    @staticmethod
    def _matches(row: dict, match: dict) -> bool:
        return all(row.get(k) == v for k, v in match.items())

    def select(self, table: str, match: dict | None = None, order: str = "created_at", desc: bool = True,
               limit: int | None = None) -> list[dict]:
        rows = [dict(r) for r in self.tables[table] if self._matches(r, match or {})]
        rows.sort(key=lambda r: r.get(order) or "", reverse=desc)
        return rows[:limit] if limit else rows

    def get(self, table: str, **match) -> dict | None:
        rows = self.select(table, match, limit=1)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> dict:
        row = dict(row)
        if table in GENERATED_IDS:
            row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now_iso())
        self.tables[table].append(row)
        return dict(row)

    def update(self, table: str, match: dict, changes: dict) -> list[dict]:
        out = []
        for r in self.tables[table]:
            if self._matches(r, match):
                r.update(changes)
                out.append(dict(r))
        return out

    def upsert(self, table: str, row: dict, key: str = "id") -> dict:
        existing = [r for r in self.tables[table] if r.get(key) == row.get(key)]
        if existing:
            existing[0].update(row)
            return dict(existing[0])
        return self.insert(table, row)


class SupabaseStore:
    kind = "supabase"

    def __init__(self, url: str, key: str, timeout: float = 5.0):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        # Older keys are JWTs ("eyJ...") and also go in Authorization. The newer
        # sb_secret_ keys are not JWTs and go in the apikey header only.
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls) -> "SupabaseStore | None":
        url = os.getenv("SUPABASE_URL", "")
        key = next((os.getenv(n) for n in ("SUPABASE_SERVICE_KEY", "SUPABASE_SECRET_KEY",
                                            "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY") if os.getenv(n)), "")
        return cls(url, key) if url and key else None

    def _check(self, r: httpx.Response) -> Any:
        if r.status_code >= 300:
            raise StoreError(f"Supabase {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    @staticmethod
    def _filters(match: dict | None) -> dict:
        return {k: f"eq.{v}" for k, v in (match or {}).items()}

    def select(self, table: str, match: dict | None = None, order: str = "created_at", desc: bool = True,
               limit: int | None = None) -> list[dict]:
        params = {"select": "*", **self._filters(match), "order": f"{order}.{'desc' if desc else 'asc'}"}
        if limit:
            params["limit"] = str(limit)
        return self._check(self.client.get(self.base + table, params=params, headers=self.headers)) or []

    def get(self, table: str, **match) -> dict | None:
        rows = self.select(table, match, limit=1)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> dict:
        h = {**self.headers, "Prefer": "return=representation"}
        return self._check(self.client.post(self.base + table, json=row, headers=h))[0]

    def update(self, table: str, match: dict, changes: dict) -> list[dict]:
        h = {**self.headers, "Prefer": "return=representation"}
        return self._check(self.client.patch(self.base + table, params=self._filters(match), json=changes, headers=h)) or []

    def upsert(self, table: str, row: dict, key: str = "id") -> dict:
        h = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
        return self._check(self.client.post(self.base + table, params={"on_conflict": key}, json=row, headers=h))[0]
