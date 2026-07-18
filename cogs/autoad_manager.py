"""Business logic for Auto Advertisement."""
from __future__ import annotations

import base64
import datetime as dt
import io
import random
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

import discord

from utils.guild_storage import GuildJSONStorage

DEFAULT_AUTOAD: dict[str, Any] = {
    "enabled": False,
    "mode": "timer",
    "interval_minutes": 60,
    "message_count": 25,
    "channels": [],
    "ads": [],
    "next_index": 0,
    "message_counter": 0,
    "stats": {"sent": 0, "manual_sent": 0, "triggered_sent": 0, "last_sent_at": None},
}


@dataclass(slots=True)
class StoredAttachment:
    """Base64-encoded attachment data for JSON storage."""

    filename: str
    content_type: str | None
    data: str

    @classmethod
    async def from_discord_attachment(cls, attachment: discord.Attachment) -> "StoredAttachment":
        """Read a Discord attachment into JSON-safe data."""
        return cls(
            filename=attachment.filename,
            content_type=attachment.content_type,
            data=base64.b64encode(await attachment.read()).decode("ascii"),
        )

    def to_file(self) -> discord.File:
        """Convert stored data back to a Discord upload."""
        return discord.File(io.BytesIO(base64.b64decode(self.data)), filename=self.filename)


class AutoAdManager:
    """Shared AutoAd data and dispatch helper methods."""

    def __init__(self) -> None:
        self.storage = GuildJSONStorage("autoad.json", DEFAULT_AUTOAD)

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        """Load a guild's AutoAd config."""
        return await self.storage.load(guild_id)

    async def save_config(self, guild_id: int, config: dict[str, Any]) -> None:
        """Save a guild's AutoAd config."""
        await self.storage.save(guild_id, config)

    async def create_ad(
        self,
        guild_id: int,
        *,
        name: str,
        message: str | None,
        image_url: str | None,
        embed_title: str | None,
        embed_description: str | None,
        attachment: discord.Attachment | None,
    ) -> dict[str, Any]:
        """Create an advertisement record."""
        config = await self.get_config(guild_id)
        attachments = []
        if attachment:
            attachments.append(asdict(await StoredAttachment.from_discord_attachment(attachment)))
        ad = {
            "id": uuid4().hex[:8],
            "name": name,
            "message": message,
            "image_url": image_url,
            "embed_title": embed_title,
            "embed_description": embed_description,
            "attachments": attachments,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "sent": 0,
        }
        config["ads"].append(ad)
        await self.save_config(guild_id, config)
        return ad

    def build_payload(self, ad: dict[str, Any]) -> tuple[str | None, discord.Embed | None, list[discord.File]]:
        """Convert an advertisement into Discord send arguments."""
        embed = None
        if ad.get("embed_title") or ad.get("embed_description") or ad.get("image_url"):
            embed = discord.Embed(
                title=ad.get("embed_title"),
                description=ad.get("embed_description"),
                color=discord.Color.blurple(),
                timestamp=dt.datetime.now(dt.UTC),
            )
            if ad.get("image_url"):
                embed.set_image(url=ad["image_url"])
            embed.set_footer(text="Ultimate Master Bot • Auto Advertisement")
        files = [StoredAttachment(**payload).to_file() for payload in ad.get("attachments", [])]
        return ad.get("message"), embed, files

    async def choose_ad(self, guild_id: int) -> dict[str, Any] | None:
        """Choose an ad according to random or rotation behavior."""
        config = await self.get_config(guild_id)
        ads = config.get("ads", [])
        if not ads:
            return None
        if config.get("mode") == "random":
            return random.choice(ads)
        index = int(config.get("next_index", 0)) % len(ads)
        config["next_index"] = (index + 1) % len(ads)
        await self.save_config(guild_id, config)
        return ads[index]

    async def record_send(self, guild_id: int, ad_id: str, *, manual: bool = False, triggered: bool = False) -> None:
        """Update ad and guild send counters."""
        config = await self.get_config(guild_id)
        for ad in config.get("ads", []):
            if ad.get("id") == ad_id:
                ad["sent"] = int(ad.get("sent", 0)) + 1
                break
        stats = config.setdefault("stats", {})
        stats["sent"] = int(stats.get("sent", 0)) + 1
        stats["manual_sent"] = int(stats.get("manual_sent", 0)) + int(manual)
        stats["triggered_sent"] = int(stats.get("triggered_sent", 0)) + int(triggered)
        stats["last_sent_at"] = dt.datetime.now(dt.UTC).isoformat()
        await self.save_config(guild_id, config)
