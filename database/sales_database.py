"""SQLite storage for the shop, purchases, balances, and sales settings."""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_PATH = Path("data/sales.sqlite3")


@dataclass(slots=True)
class Product:
    id: int
    guild_id: int
    name: str
    description: str
    price: int
    stock: int
    image_url: str | None
    active: bool
    created_at: str
    updated_at: str


@dataclass(slots=True)
class Purchase:
    id: int
    guild_id: int
    user_id: int
    product_id: int
    product_name: str
    quantity: int
    total_price: int
    purchased_at: str


class SalesDatabase:
    """Async-safe SQLite facade for shop operations."""

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
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price INTEGER NOT NULL CHECK (price >= 0),
                    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                    image_url TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_products_guild_active ON products(guild_id, active);

                CREATE TABLE IF NOT EXISTS balances (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    total_price INTEGER NOT NULL CHECK (total_price >= 0),
                    purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_purchases_guild ON purchases(guild_id, purchased_at);
                CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(guild_id, user_id);

                CREATE TABLE IF NOT EXISTS sales_config (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    @staticmethod
    def _product(row: sqlite3.Row | None) -> Product | None:
        if row is None:
            return None
        return Product(
            id=int(row["id"]), guild_id=int(row["guild_id"]), name=str(row["name"]),
            description=str(row["description"]), price=int(row["price"]), stock=int(row["stock"]),
            image_url=row["image_url"], active=bool(row["active"]),
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _purchase(row: sqlite3.Row) -> Purchase:
        return Purchase(
            id=int(row["id"]), guild_id=int(row["guild_id"]), user_id=int(row["user_id"]),
            product_id=int(row["product_id"]), product_name=str(row["product_name"]),
            quantity=int(row["quantity"]), total_price=int(row["total_price"]), purchased_at=str(row["purchased_at"]),
        )

    async def add_product(self, guild_id: int, name: str, description: str, price: int, stock: int, image_url: str | None) -> Product:
        async with self._lock:
            return await asyncio.to_thread(self._add_product_sync, guild_id, name, description, price, stock, image_url)

    def _add_product_sync(self, guild_id: int, name: str, description: str, price: int, stock: int, image_url: str | None) -> Product:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO products (guild_id, name, description, price, stock, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, name, description, price, stock, image_url),
            )
            return self._product(conn.execute("SELECT * FROM products WHERE id = ?", (cur.lastrowid,)).fetchone())  # type: ignore[return-value]

    async def list_products(self, guild_id: int, *, active_only: bool = True) -> list[Product]:
        async with self._lock:
            return await asyncio.to_thread(self._list_products_sync, guild_id, active_only)

    def _list_products_sync(self, guild_id: int, active_only: bool) -> list[Product]:
        sql = "SELECT * FROM products WHERE guild_id = ?"
        params: list[Any] = [guild_id]
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY active DESC, id ASC"
        with self._connect() as conn:
            return [self._product(row) for row in conn.execute(sql, params).fetchall() if self._product(row)]  # type: ignore[misc]

    async def get_product(self, guild_id: int, product_id: int) -> Product | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_product_sync, guild_id, product_id)

    def _get_product_sync(self, guild_id: int, product_id: int) -> Product | None:
        with self._connect() as conn:
            return self._product(conn.execute("SELECT * FROM products WHERE guild_id = ? AND id = ?", (guild_id, product_id)).fetchone())

    async def update_product(self, guild_id: int, product_id: int, **fields: Any) -> Product | None:
        allowed = {"name", "description", "price", "stock", "image_url", "active"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return await self.get_product(guild_id, product_id)
        async with self._lock:
            return await asyncio.to_thread(self._update_product_sync, guild_id, product_id, updates)

    def _update_product_sync(self, guild_id: int, product_id: int, updates: dict[str, Any]) -> Product | None:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [guild_id, product_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE products SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND id = ?", params)
            return self._product(conn.execute("SELECT * FROM products WHERE guild_id = ? AND id = ?", (guild_id, product_id)).fetchone())

    async def add_stock(self, guild_id: int, product_id: int, amount: int) -> Product | None:
        async with self._lock:
            return await asyncio.to_thread(self._stock_sync, guild_id, product_id, amount)

    def _stock_sync(self, guild_id: int, product_id: int, amount: int) -> Product | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE products SET stock = MAX(stock + ?, 0), updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND id = ?",
                (amount, guild_id, product_id),
            )
            return self._product(conn.execute("SELECT * FROM products WHERE guild_id = ? AND id = ?", (guild_id, product_id)).fetchone())

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._get_balance_sync, guild_id, user_id)

    def _get_balance_sync(self, guild_id: int, user_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT balance FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
            return int(row["balance"]) if row else 0

    async def add_balance(self, guild_id: int, user_id: int, amount: int) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._add_balance_sync, guild_id, user_id, amount)

    def _add_balance_sync(self, guild_id: int, user_id: int, amount: int) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT balance FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
            current = int(row["balance"]) if row else 0
            new_balance = max(current + amount, 0)
            conn.execute(
                "INSERT INTO balances (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance, updated_at = CURRENT_TIMESTAMP",
                (guild_id, user_id, new_balance),
            )
            conn.execute("COMMIT")
            return new_balance

    async def purchase(self, guild_id: int, user_id: int, product_id: int, quantity: int = 1) -> tuple[bool, str, Purchase | None, int]:
        async with self._lock:
            return await asyncio.to_thread(self._purchase_sync, guild_id, user_id, product_id, quantity)

    def _purchase_sync(self, guild_id: int, user_id: int, product_id: int, quantity: int) -> tuple[bool, str, Purchase | None, int]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM products WHERE guild_id = ? AND id = ? AND active = 1", (guild_id, product_id)).fetchone()
                product = self._product(row)
                if not product:
                    conn.execute("ROLLBACK")
                    return False, "المنتج غير موجود أو غير مفعل.", None, 0
                if quantity < 1 or product.stock < quantity:
                    conn.execute("ROLLBACK")
                    return False, "المخزون غير كافٍ.", None, 0
                balance_row = conn.execute("SELECT balance FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
                balance = int(balance_row["balance"]) if balance_row else 0
                total = product.price * quantity
                if balance < total:
                    conn.execute("ROLLBACK")
                    return False, f"رصيدك غير كافٍ. تحتاج {total} ولديك {balance}.", None, balance
                new_balance = balance - total
                conn.execute("UPDATE products SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND id = ?", (quantity, guild_id, product_id))
                conn.execute(
                    "INSERT INTO balances (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance, updated_at = CURRENT_TIMESTAMP",
                    (guild_id, user_id, new_balance),
                )
                cur = conn.execute(
                    "INSERT INTO purchases (guild_id, user_id, product_id, product_name, quantity, total_price) VALUES (?, ?, ?, ?, ?, ?)",
                    (guild_id, user_id, product.id, product.name, quantity, total),
                )
                purchase = self._purchase(conn.execute("SELECT * FROM purchases WHERE id = ?", (cur.lastrowid,)).fetchone())
                conn.execute("COMMIT")
                return True, "تمت عملية الشراء بنجاح.", purchase, new_balance
            except Exception:
                conn.execute("ROLLBACK")
                raise

    async def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_log_channel_sync, guild_id, channel_id)

    def _set_log_channel_sync(self, guild_id: int, channel_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sales_config (guild_id, log_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id, updated_at = CURRENT_TIMESTAMP",
                (guild_id, channel_id),
            )

    async def get_log_channel(self, guild_id: int) -> int | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_log_channel_sync, guild_id)

    def _get_log_channel_sync(self, guild_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT log_channel_id FROM sales_config WHERE guild_id = ?", (guild_id,)).fetchone()
            return int(row["log_channel_id"]) if row and row["log_channel_id"] else None
