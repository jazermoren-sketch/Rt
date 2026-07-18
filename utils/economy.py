"""Economy integration layer for shop purchases."""
from __future__ import annotations

from database.sales_database import SalesDatabase


class EconomyService:
    """Small adapter that uses the shared sales database balance table.

    No separate economy module exists in this repository, so this adapter keeps
    balances centralized and can be replaced later by an existing economy cog.
    """

    def __init__(self, database: SalesDatabase) -> None:
        self.database = database

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        return await self.database.get_balance(guild_id, user_id)

    async def add_balance(self, guild_id: int, user_id: int, amount: int) -> int:
        return await self.database.add_balance(guild_id, user_id, amount)
