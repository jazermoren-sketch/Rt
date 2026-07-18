"""SQLite storage for secure marketplace listings, settings, warnings, and scam reports."""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_PATH = Path("data/marketplace.sqlite3")


@dataclass(slots=True)
class MarketplaceListing:
    id: int; guild_id: int; seller_id: int; seller_name: str; title: str; category: str
    description: str; price: str; channel_id: int | None; evidence: str | None; image_url: str | None
    status: str; created_at: str; updated_at: str


@dataclass(slots=True)
class ScamReportRecord:
    id: int; guild_id: int; reporter_id: int; accused_id: int | None; accused_text: str
    details: str; amount: str | None; evidence: str | None; status: str; created_at: str; updated_at: str


class MarketplaceDatabase:
    """Async-safe SQLite facade for marketplace operations."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._ready = False

    async def initialize(self) -> None:
        async with self._lock:
            if self._ready:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._ready = True

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS marketplace_settings (
                    guild_id INTEGER PRIMARY KEY,
                    marketplace_channel_id INTEGER,
                    scam_reports_channel_id INTEGER,
                    logs_channel_id INTEGER,
                    product_creation_channels TEXT NOT NULL DEFAULT '[]',
                    privacy_channels TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS marketplace_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    seller_id INTEGER NOT NULL,
                    seller_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    description TEXT NOT NULL,
                    price TEXT NOT NULL,
                    channel_id INTEGER,
                    evidence TEXT,
                    image_url TEXT,
                    status TEXT NOT NULL DEFAULT 'Active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_marketplace_listing_guild ON marketplace_listings(guild_id, status, created_at);
                CREATE TABLE IF NOT EXISTS marketplace_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    seller_id INTEGER NOT NULL,
                    admin_id INTEGER NOT NULL,
                    listing_id INTEGER,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS scam_reports_secure (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    accused_id INTEGER,
                    accused_text TEXT NOT NULL,
                    details TEXT NOT NULL,
                    amount TEXT,
                    evidence TEXT,
                    status TEXT NOT NULL DEFAULT 'Pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_scam_reports_guild ON scam_reports_secure(guild_id, status, created_at);
                """
            )

    @staticmethod
    def _listing(row: sqlite3.Row | None) -> MarketplaceListing | None:
        if row is None: return None
        return MarketplaceListing(**{k: row[k] for k in row.keys()})

    @staticmethod
    def _report(row: sqlite3.Row | None) -> ScamReportRecord | None:
        if row is None: return None
        return ScamReportRecord(**{k: row[k] for k in row.keys()})

    async def create_listing(self, **data: Any) -> MarketplaceListing:
        async with self._lock:
            return await asyncio.to_thread(self._create_listing_sync, data)

    def _create_listing_sync(self, data: dict[str, Any]) -> MarketplaceListing:
        keys = ["guild_id", "seller_id", "seller_name", "title", "category", "description", "price", "channel_id", "evidence", "image_url"]
        with self._connect() as conn:
            cur = conn.execute(f"INSERT INTO marketplace_listings ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})", [data.get(k) for k in keys])
            return self._listing(conn.execute("SELECT * FROM marketplace_listings WHERE id = ?", (cur.lastrowid,)).fetchone())  # type: ignore[return-value]

    async def list_listings(self, guild_id: int, *, active_only: bool = True, seller_id: int | None = None) -> list[MarketplaceListing]:
        async with self._lock:
            return await asyncio.to_thread(self._list_listings_sync, guild_id, active_only, seller_id)

    def _list_listings_sync(self, guild_id: int, active_only: bool, seller_id: int | None) -> list[MarketplaceListing]:
        sql = "SELECT * FROM marketplace_listings WHERE guild_id = ?"; params: list[Any] = [guild_id]
        if active_only: sql += " AND status = 'Active'"
        if seller_id is not None: sql += " AND seller_id = ?"; params.append(seller_id)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            return [item for row in conn.execute(sql, params).fetchall() if (item := self._listing(row))]

    async def get_listing(self, guild_id: int, listing_id: int) -> MarketplaceListing | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_listing_sync, guild_id, listing_id)

    def _get_listing_sync(self, guild_id: int, listing_id: int) -> MarketplaceListing | None:
        with self._connect() as conn:
            return self._listing(conn.execute("SELECT * FROM marketplace_listings WHERE guild_id = ? AND id = ?", (guild_id, listing_id)).fetchone())

    async def update_listing(self, guild_id: int, listing_id: int, **fields: Any) -> MarketplaceListing | None:
        allowed = {"title", "category", "description", "price", "channel_id", "evidence", "image_url", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        async with self._lock:
            return await asyncio.to_thread(self._update_listing_sync, guild_id, listing_id, updates)

    def _update_listing_sync(self, guild_id: int, listing_id: int, updates: dict[str, Any]) -> MarketplaceListing | None:
        with self._connect() as conn:
            if updates:
                conn.execute(f"UPDATE marketplace_listings SET {', '.join(f'{k} = ?' for k in updates)}, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND id = ?", list(updates.values()) + [guild_id, listing_id])
            return self._listing(conn.execute("SELECT * FROM marketplace_listings WHERE guild_id = ? AND id = ?", (guild_id, listing_id)).fetchone())

    async def add_warning(self, guild_id: int, seller_id: int, admin_id: int, listing_id: int | None, reason: str) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._add_warning_sync, guild_id, seller_id, admin_id, listing_id, reason)

    def _add_warning_sync(self, guild_id: int, seller_id: int, admin_id: int, listing_id: int | None, reason: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO marketplace_warnings (guild_id, seller_id, admin_id, listing_id, reason) VALUES (?, ?, ?, ?, ?)", (guild_id, seller_id, admin_id, listing_id, reason))
            return int(cur.lastrowid)

    async def warning_count(self, guild_id: int, seller_id: int) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._warning_count_sync, guild_id, seller_id)

    def _warning_count_sync(self, guild_id: int, seller_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM marketplace_warnings WHERE guild_id = ? AND seller_id = ?", (guild_id, seller_id)).fetchone()
            return int(row["count"])

    async def create_report(self, **data: Any) -> ScamReportRecord:
        async with self._lock:
            return await asyncio.to_thread(self._create_report_sync, data)

    def _create_report_sync(self, data: dict[str, Any]) -> ScamReportRecord:
        keys = ["guild_id", "reporter_id", "accused_id", "accused_text", "details", "amount", "evidence"]
        with self._connect() as conn:
            cur = conn.execute(f"INSERT INTO scam_reports_secure ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})", [data.get(k) for k in keys])
            return self._report(conn.execute("SELECT * FROM scam_reports_secure WHERE id = ?", (cur.lastrowid,)).fetchone())  # type: ignore[return-value]

    async def update_report_status(self, guild_id: int, report_id: int, status: str) -> ScamReportRecord | None:
        async with self._lock:
            return await asyncio.to_thread(self._update_report_status_sync, guild_id, report_id, status)

    def _update_report_status_sync(self, guild_id: int, report_id: int, status: str) -> ScamReportRecord | None:
        with self._connect() as conn:
            conn.execute("UPDATE scam_reports_secure SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND id = ?", (status, guild_id, report_id))
            return self._report(conn.execute("SELECT * FROM scam_reports_secure WHERE guild_id = ? AND id = ?", (guild_id, report_id)).fetchone())

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._get_settings_sync, guild_id)

    def _get_settings_sync(self, guild_id: int) -> dict[str, Any]:
        import json
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO marketplace_settings (guild_id) VALUES (?)", (guild_id,))
            row = conn.execute("SELECT * FROM marketplace_settings WHERE guild_id = ?", (guild_id,)).fetchone()
            data = dict(row)
            data["product_creation_channels"] = json.loads(data.get("product_creation_channels") or "[]")
            data["privacy_channels"] = json.loads(data.get("privacy_channels") or "[]")
            return data

    async def set_channel(self, guild_id: int, key: str, channel_id: int) -> None:
        if key not in {"marketplace_channel_id", "scam_reports_channel_id", "logs_channel_id"}:
            raise ValueError("invalid channel setting")
        async with self._lock:
            await asyncio.to_thread(self._set_channel_sync, guild_id, key, channel_id)

    def _set_channel_sync(self, guild_id: int, key: str, channel_id: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO marketplace_settings (guild_id) VALUES (?)", (guild_id,))
            conn.execute(f"UPDATE marketplace_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?", (channel_id, guild_id))

    async def toggle_list_channel(self, guild_id: int, key: str, channel_id: int, enabled: bool) -> list[int]:
        if key not in {"product_creation_channels", "privacy_channels"}:
            raise ValueError("invalid list setting")
        async with self._lock:
            return await asyncio.to_thread(self._toggle_list_channel_sync, guild_id, key, channel_id, enabled)

    def _toggle_list_channel_sync(self, guild_id: int, key: str, channel_id: int, enabled: bool) -> list[int]:
        import json
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO marketplace_settings (guild_id) VALUES (?)", (guild_id,))
            row = conn.execute(f"SELECT {key} FROM marketplace_settings WHERE guild_id = ?", (guild_id,)).fetchone()
            values = set(json.loads(row[key] or "[]"))
            values.add(channel_id) if enabled else values.discard(channel_id)
            result = sorted(values)
            conn.execute(f"UPDATE marketplace_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?", (json.dumps(result), guild_id))
            return result
