"""Minimal startup file for Ultimate Master Bot."""
from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

EXTENSIONS = (
    "cogs.autoad",
    "cogs.sales_moderation",
    "cogs.scam_report",
)


def build_bot() -> commands.Bot:
    """Create the Discord bot instance."""
    intents = discord.Intents.default()
    intents.message_content = True
    return commands.Bot(command_prefix="!", intents=intents)


bot = build_bot()


@bot.event
async def on_ready() -> None:
    """Log readiness and sync slash commands."""
    user = bot.user.name if bot.user else "Unknown"
    LOGGER.info("Ultimate Bot Online: %s", user)
    try:
        synced = await bot.tree.sync()
        LOGGER.info("Synced %s slash commands", len(synced))
    except Exception:
        LOGGER.exception("Slash command sync failed")


async def main() -> None:
    """Load extensions and start the bot."""
    token = "YOUR_BOT_TOKEN"

    async with bot:
        for extension in EXTENSIONS:
            await bot.load_extension(extension)
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
