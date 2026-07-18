"""Auto Advertisement slash-command cog."""
from __future__ import annotations

import datetime as dt
import io
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.autoad_manager import AutoAdManager
from utils.embed_factory import ERROR_COLOR, SUCCESS_COLOR, make_embed
from utils.permissions import admin_only
from views.autoad_views import AutoAdModeSelectView, AutoAdPreviewView

LOGGER = logging.getLogger(__name__)


class AutoAdCog(commands.Cog):
    """Auto Advertisement system with per-guild settings."""

    autoad = app_commands.Group(name="autoad", description="Manage automatic advertisements")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.manager = AutoAdManager()
        self.timer_loop.start()

    async def cog_unload(self) -> None:
        self.timer_loop.cancel()

    async def send_autoad(self, channel: discord.abc.Messageable, guild_id: int, *, manual: bool = False, triggered: bool = False) -> bool:
        """Send the next advertisement into a channel."""
        ad = await self.manager.choose_ad(guild_id)
        if not ad:
            return False
        content, embed, files = self.manager.build_payload(ad)
        await channel.send(content=content, embed=embed, files=files, allowed_mentions=discord.AllowedMentions.none())
        await self.manager.record_send(guild_id, ad["id"], manual=manual, triggered=triggered)
        return True

    async def send_specific_ad(self, channel: discord.abc.Messageable, guild_id: int, ad_id: str, *, manual: bool = False) -> bool:
        """Send a specific advertisement by ID."""
        config = await self.manager.get_config(guild_id)
        ad = next((item for item in config.get("ads", []) if item.get("id") == ad_id), None)
        if not ad:
            return False
        content, embed, files = self.manager.build_payload(ad)
        await channel.send(content=content, embed=embed, files=files, allowed_mentions=discord.AllowedMentions.none())
        await self.manager.record_send(guild_id, ad_id, manual=manual)
        return True

    async def delete_ad(self, guild_id: int, ad_id: str) -> bool:
        """Delete an advertisement by ID."""
        config = await self.manager.get_config(guild_id)
        before = len(config.get("ads", []))
        config["ads"] = [ad for ad in config.get("ads", []) if ad.get("id") != ad_id]
        await self.manager.save_config(guild_id, config)
        return len(config["ads"]) < before

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Trigger every-message and message-count AutoAds safely."""
        if not message.guild or message.author.bot or message.webhook_id:
            return
        config = await self.manager.get_config(message.guild.id)
        channels = [int(channel_id) for channel_id in config.get("channels", [])]
        if not config.get("enabled") or message.channel.id not in channels:
            return
        mode = config.get("mode")
        if mode == "every_message":
            await self.send_autoad(message.channel, message.guild.id, triggered=True)
        elif mode == "message_count":
            config["message_counter"] = int(config.get("message_counter", 0)) + 1
            if config["message_counter"] >= int(config.get("message_count", 25)):
                config["message_counter"] = 0
                await self.manager.save_config(message.guild.id, config)
                await self.send_autoad(message.channel, message.guild.id, triggered=True)
            else:
                await self.manager.save_config(message.guild.id, config)

    @tasks.loop(minutes=1)
    async def timer_loop(self) -> None:
        """Send timer-mode AutoAds at configured intervals."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            config = await self.manager.get_config(guild.id)
            if not config.get("enabled") or config.get("mode") != "timer":
                continue
            last = config.get("stats", {}).get("last_sent_at")
            due = True
            if last:
                try:
                    due = (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last)).total_seconds() >= int(config.get("interval_minutes", 60)) * 60
                except ValueError:
                    due = True
            if not due:
                continue
            for channel_id in config.get("channels", []):
                channel = guild.get_channel(int(channel_id))
                if isinstance(channel, discord.TextChannel):
                    try:
                        await self.send_autoad(channel, guild.id, triggered=True)
                    except discord.HTTPException:
                        LOGGER.exception("Failed to send timer AutoAd in guild %s channel %s", guild.id, channel_id)

    @autoad.command(name="create", description="Create an advertisement")
    @admin_only()
    async def create(self, interaction: discord.Interaction, name: str, message: str | None = None, image_url: str | None = None, embed_title: str | None = None, embed_description: str | None = None, attachment: discord.Attachment | None = None) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if not any([message, image_url, embed_title, embed_description, attachment]):
            await interaction.followup.send(embed=make_embed("Nothing to save", "Provide message text, an image URL, an embed field, or an attachment.", color=ERROR_COLOR))
            return
        ad = await self.manager.create_ad(interaction.guild.id, name=name, message=message, image_url=image_url, embed_title=embed_title, embed_description=embed_description, attachment=attachment)
        await interaction.followup.send(embed=make_embed("Advertisement created", f"Saved `{ad['name']}` with ID `{ad['id']}`.", color=SUCCESS_COLOR))

    @autoad.command(name="edit", description="Edit advertisement text or image by ID")
    @admin_only()
    async def edit(self, interaction: discord.Interaction, ad_id: str, message: str | None = None, image_url: str | None = None) -> None:
        if not interaction.guild:
            return
        config = await self.manager.get_config(interaction.guild.id)
        for ad in config["ads"]:
            if ad["id"] == ad_id:
                if message is not None:
                    ad["message"] = message
                if image_url is not None:
                    ad["image_url"] = image_url
                await self.manager.save_config(interaction.guild.id, config)
                await interaction.response.send_message(embed=make_embed("Advertisement updated", f"Updated `{ad_id}`.", color=SUCCESS_COLOR), ephemeral=True)
                return
        await interaction.response.send_message(embed=make_embed("Not found", f"No advertisement with ID `{ad_id}`.", color=ERROR_COLOR), ephemeral=True)

    @autoad.command(name="delete", description="Delete an advertisement by ID")
    @admin_only()
    async def delete(self, interaction: discord.Interaction, ad_id: str) -> None:
        if not interaction.guild:
            return
        ok = await self.delete_ad(interaction.guild.id, ad_id)
        await interaction.response.send_message(embed=make_embed("Deleted" if ok else "Not found", f"Advertisement `{ad_id}`.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)

    @autoad.command(name="list", description="List advertisements")
    @admin_only()
    async def list_ads(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        config = await self.manager.get_config(interaction.guild.id)
        embed = make_embed("Auto Advertisements")
        for ad in config.get("ads", [])[:25]:
            embed.add_field(name=f"{ad['name']} (`{ad['id']}`)", value=f"Sent: {ad.get('sent', 0)}", inline=False)
        if not embed.fields:
            embed.description = "No advertisements have been created."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @autoad.command(name="channel", description="Enable or disable a channel for AutoAd")
    @admin_only()
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        enabled: bool = True,
    ) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer(ephemeral=True)

        config = await self.manager.get_config(interaction.guild.id)

        channels = set(map(int, config.get("channels", [])))

        if enabled:
            channels.add(channel.id)
        else:
            channels.discard(channel.id)

        config["channels"] = sorted(channels)

        await self.manager.save_config(interaction.guild.id, config)

        await interaction.followup.send(
            embed=make_embed(
                "Channels updated",
                f"{channel.mention} is {'enabled' if enabled else 'disabled'} for AutoAd.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )
        
    @autoad.command(name="send", description="Test send the next advertisement")
    @admin_only()
    async def send(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        if not interaction.guild:
            return
        target = channel or interaction.channel
        ok = await self.send_autoad(target, interaction.guild.id, manual=True) if target else False
        await interaction.response.send_message(embed=make_embed("Sent" if ok else "No ads", "Manual advertisement dispatch complete.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)

    @autoad.command(name="channel", description="Add or remove an AutoAd channel")
    @admin_only()
    @autoad.command(name="channel", description="Enable or disable a channel for AutoAd")
@admin_only()
async def channel(
    self,
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    enabled: bool = True,
) -> None:
    if not interaction.guild:
        return

    await interaction.response.defer(ephemeral=True)

    config = await self.manager.get_config(interaction.guild.id)

    channels = set(map(int, config.get("channels", [])))

    if enabled:
        channels.add(channel.id)
    else:
        channels.discard(channel.id)

    config["channels"] = sorted(channels)

    await self.manager.save_config(interaction.guild.id, config)

    await interaction.followup.send(
        embed=make_embed(
            "Channels updated",
            f"{channel.mention} is {'enabled' if enabled else 'disabled'} for AutoAd.",
            color=SUCCESS_COLOR,
        ),
        ephemeral=True,
    )
    
    async def _set_number(self, interaction: discord.Interaction, key: str, value: int, label: str) -> None:
        if not interaction.guild:
            return
        config = await self.manager.get_config(interaction.guild.id)
        config[key] = value
        await self.manager.save_config(interaction.guild.id, config)
        await interaction.response.send_message(embed=make_embed(f"{label} updated", f"Set to `{value}`.", color=SUCCESS_COLOR), ephemeral=True)

    @autoad.command(name="status", description="Show AutoAd status")
    @admin_only()
    async def status(self, interaction: discord.Interaction) -> None:
        await self._show_config(interaction, include_stats=False)

    @autoad.command(name="stats", description="Show AutoAd statistics")
    @admin_only()
    async def stats(self, interaction: discord.Interaction) -> None:
        await self._show_config(interaction, include_stats=True)

    async def _show_config(self, interaction: discord.Interaction, *, include_stats: bool) -> None:
        if not interaction.guild:
            return
        config = await self.manager.get_config(interaction.guild.id)
        embed = make_embed("AutoAd Status")
        embed.add_field(name="Enabled", value=str(config.get("enabled")), inline=True)
        embed.add_field(name="Mode", value=str(config.get("mode")), inline=True)
        embed.add_field(name="Ads", value=str(len(config.get("ads", []))), inline=True)
        embed.add_field(name="Channels", value=", ".join(f"<#{cid}>" for cid in config.get("channels", [])) or "None", inline=False)
        if include_stats:
            stats = config.get("stats", {})
            embed.add_field(name="Total sent", value=str(stats.get("sent", 0)), inline=True)
            embed.add_field(name="Manual sent", value=str(stats.get("manual_sent", 0)), inline=True)
            embed.add_field(name="Triggered sent", value=str(stats.get("triggered_sent", 0)), inline=True)
        view = None if include_stats else AutoAdModeSelectView(self, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @autoad.command(name="export", description="Export AutoAd JSON")
    @admin_only()
    async def export(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        config = await self.manager.get_config(interaction.guild.id)
        payload = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")
        await interaction.response.send_message(file=discord.File(io.BytesIO(payload), filename="autoad.json"), ephemeral=True)

    @autoad.command(name="import", description="Import AutoAd JSON")
    @admin_only()
    async def import_config(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            data = json.loads((await file.read()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await interaction.followup.send(embed=make_embed("Invalid JSON", "Upload a valid AutoAd export.", color=ERROR_COLOR))
            return
        await self.manager.save_config(interaction.guild.id, data)
        await interaction.followup.send(embed=make_embed("Imported", "AutoAd configuration imported.", color=SUCCESS_COLOR))


async def setup(bot: commands.Bot) -> None:
    """Load the AutoAd cog."""
    await bot.add_cog(AutoAdCog(bot))
