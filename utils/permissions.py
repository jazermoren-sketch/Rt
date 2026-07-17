"""Reusable Discord permission checks."""
from __future__ import annotations

import discord
from discord import app_commands


def has_administrator(member: discord.abc.User) -> bool:
    """Return whether a member-like object has administrator permission."""
    permissions = getattr(member, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


def admin_only() -> app_commands.Check:
    """Application-command check requiring administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if has_administrator(interaction.user):
            return True
        raise app_commands.CheckFailure("Administrator permission is required.")

    return app_commands.check(predicate)
