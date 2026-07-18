"""Reusable Discord permission checks for prefix and slash commands."""
from __future__ import annotations

from collections.abc import Iterable

import discord
from discord import app_commands
from discord.ext import commands

ADMIN_DENIED_MESSAGE = "❌ لا تملك صلاحية Administrator لاستخدام هذا الأمر."


def has_administrator(user: discord.abc.User) -> bool:
    """Return whether a user/member has administrator permission."""
    permissions = getattr(user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


def has_any_role(user: discord.abc.User, role_ids: Iterable[int]) -> bool:
    """Return whether a member has any role ID from role_ids."""
    wanted = {int(role_id) for role_id in role_ids}
    roles = getattr(user, "roles", [])
    return any(getattr(role, "id", None) in wanted for role in roles)


async def _deny_interaction(interaction: discord.Interaction, message: str = ADMIN_DENIED_MESSAGE) -> None:
    """Send a single ephemeral denial message without double-responding."""
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def admin_only() -> app_commands.Check:
    """Application-command check requiring Administrator permission.

    The predicate sends a user-friendly ephemeral denial response before failing
    the check, which prevents silent interaction failures for unauthorized users.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if has_administrator(interaction.user):
            return True
        await _deny_interaction(interaction)
        return False

    return app_commands.check(predicate)


def prefix_admin_only() -> commands.Check:
    """Prefix-command check requiring Administrator permission."""

    async def predicate(ctx: commands.Context) -> bool:
        return has_administrator(ctx.author)

    return commands.check(predicate)
