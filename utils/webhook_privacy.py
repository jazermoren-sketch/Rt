"""Webhook privacy helpers for marketplace channels."""
from __future__ import annotations

import discord

from utils.franco import to_franco


async def relay_private_message(message: discord.Message, *, transform_text: bool = True) -> bool:
    """Relay a message through a channel webhook without exposing sender identity.

    Returns True when the message was relayed and original deletion was attempted.
    Webhook messages and bot messages are ignored to prevent loops.
    """
    if message.author.bot or message.webhook_id or not isinstance(message.channel, discord.TextChannel):
        return False
    content = to_franco(message.content) if transform_text else (message.content or "")
    files = [await attachment.to_file() for attachment in message.attachments]
    if not content and not files:
        return False
    webhook = None
    for existing in await message.channel.webhooks():
        if existing.name == "MarketplacePrivacy":
            webhook = existing
            break
    if webhook is None:
        webhook = await message.channel.create_webhook(name="MarketplacePrivacy", reason="Marketplace privacy relay")
    await webhook.send(
        content=content or None,
        username="Marketplace Seller",
        avatar_url=message.guild.icon.url if message.guild and message.guild.icon else None,
        files=files,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    return True
