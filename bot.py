"""Production entrypoint for Ultimate Master Discord Bot."""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import pkgutil
from collections.abc import Iterable

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)
COGS_PACKAGE = "cogs"


def discover_extensions(package_name: str = COGS_PACKAGE) -> tuple[str, ...]:
    """Return importable cog modules that expose an async setup function."""
    package = importlib.import_module(package_name)
    package_paths: Iterable[str] = getattr(package, "__path__", [])
    extensions: list[str] = []
    for module_info in pkgutil.iter_modules(package_paths, prefix=f"{package_name}."):
        if module_info.ispkg:
            continue
        module = importlib.import_module(module_info.name)
        setup = getattr(module, "setup", None)
        if inspect.iscoroutinefunction(setup):
            extensions.append(module_info.name)
        else:
            LOGGER.warning("Skipping %s because it has no async setup(bot) entrypoint", module_info.name)
    return tuple(sorted(extensions))


EXTENSIONS = discover_extensions()


def build_bot() -> commands.Bot:
    """Create the Discord bot instance with required intents."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    return commands.Bot(command_prefix="!", intents=intents)


bot = build_bot()


@bot.event
async def on_ready() -> None:
    """Log readiness and sync slash commands once Discord is connected."""
    user = bot.user.name if bot.user else "Unknown"
    LOGGER.info("Ultimate Master Bot online as %s", user)
    try:
        synced = await bot.tree.sync()
    except discord.HTTPException:
        LOGGER.exception("Slash command sync failed due to Discord HTTP error")
    except Exception:
        LOGGER.exception("Unexpected slash command sync failure")
    else:
        LOGGER.info("Synced %s slash commands", len(synced))


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Return a clean response for slash-command permission and runtime errors."""
    message = "❌ حدث خطأ أثناء تنفيذ الأمر."
    if isinstance(error, app_commands.CheckFailure):
        if interaction.response.is_done():
            LOGGER.info("Slash command check failed after a denial response was already sent: %s", error)
            return
        message = "❌ لا تملك الصلاحية لاستخدام هذا الأمر."
    LOGGER.warning("Slash command error: %s", error, exc_info=not isinstance(error, app_commands.CheckFailure))
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def load_extensions(bot_instance: commands.Bot, extensions: Iterable[str] = EXTENSIONS) -> None:
    """Load every discovered extension and raise if any extension fails."""
    failures: dict[str, Exception] = {}
    for extension in extensions:
        try:
            await bot_instance.load_extension(extension)
        except Exception as exc:
            failures[extension] = exc
            LOGGER.exception("Failed to load extension: %s", extension)
        else:
            LOGGER.info("Loaded extension: %s", extension)
    if failures:
        failed = ", ".join(sorted(failures))
        raise RuntimeError(f"Failed to load required extensions: {failed}")


async def main() -> None:
    """Load environment, extensions, and start the bot."""
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is required to start the bot.")
    if not EXTENSIONS:
        raise RuntimeError("No valid cogs were discovered in the cogs package.")

    async with bot:
        await load_extensions(bot)
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
