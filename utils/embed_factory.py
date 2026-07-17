"""Consistent embed styling for Ultimate Master Bot."""
from __future__ import annotations

import datetime as dt

import discord

BRAND_COLOR = discord.Color.blurple()
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
WARNING_COLOR = discord.Color.gold()
FOOTER_TEXT = "Ultimate Master Bot"


def make_embed(title: str, description: str | None = None, *, color: discord.Color = BRAND_COLOR) -> discord.Embed:
    """Build a consistently styled embed."""
    embed = discord.Embed(title=title, description=description, color=color, timestamp=dt.datetime.now(dt.UTC))
    embed.set_footer(text=FOOTER_TEXT)
    return embed


def success_embed(title: str, description: str | None = None) -> discord.Embed:
    """Build a success embed."""
    return make_embed(title, description, color=SUCCESS_COLOR)


def error_embed(title: str, description: str | None = None) -> discord.Embed:
    """Build an error embed."""
    return make_embed(title, description, color=ERROR_COLOR)
