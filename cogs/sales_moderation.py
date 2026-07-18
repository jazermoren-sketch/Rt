"""Sales relay and warning moderation cog."""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

from views.sales_views import MainSalesView, PunishmentView

LOGGER = logging.getLogger(__name__)
CHANNELS_FILE = Path("channels.txt")
LOG_CHANNEL_FILE = Path("log_channel.txt")
WARNINGS_DB = Path("warnings_db.json")
CONFIG_FILE = Path("mod_config.json")
DEFAULT_CONFIG: dict[str, Any] = {"max_warns": 3, "action": "kick"}

ARABIC_TO_FRANKO = {
    "ح": "7",
    "ع": "3",
    "خ": "5",
    "ط": "6",
    "ص": "9",
    "ض": "d",
    "ق": "8",
    "ء": "2",
    "ؤ": "2",
    "ئ": "2",
    "أ": "1",
    "إ": "1",
    "آ": "1",
}


def load_list(path: Path) -> list[int]:
    """Load integer IDs from a newline-delimited text file."""
    if not path.exists():
        return []
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip().isdigit()]


def save_list(path: Path, data: list[int]) -> None:
    """Save integer IDs to a newline-delimited text file."""
    path.write_text("".join(f"{item}\n" for item in sorted(set(data))), encoding="utf-8")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """Load JSON with a safe default."""
    if not path.exists():
        return default.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("Ignoring invalid JSON in %s", path)
        return default.copy()
    if isinstance(data, dict):
        merged = default.copy()
        merged.update(data)
        return merged
    return default.copy()


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Save JSON data."""
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def normalize_sales_text(text: str) -> str:
    """Convert configured Arabic characters to their Franko alternatives."""
    for arabic, franko in ARABIC_TO_FRANKO.items():
        text = text.replace(arabic, franko)
    return text


class SalesModerationCog(commands.Cog):
    """Relay sales posts through webhooks and manage seller warnings."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.allowed_channels = load_list(CHANNELS_FILE)
        log_channels = load_list(LOG_CHANNEL_FILE)
        self.warn_log_channel_id = log_channels[0] if log_channels else None
        self.mod_config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.webhooks_cache: dict[int, discord.Webhook] = {}

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook:
        cached = self.webhooks_cache.get(channel.id)
        if cached is not None:
            return cached
        for webhook in await channel.webhooks():
            if webhook.user == self.bot.user and webhook.name.startswith("Sales_"):
                self.webhooks_cache[channel.id] = webhook
                return webhook
        webhook = await channel.create_webhook(name=f"Sales_{channel.name[:70]}", reason="Sales relay webhook")
        self.webhooks_cache[channel.id] = webhook
        return webhook

    def _warning_embed(
        self,
        interaction: discord.Interaction,
        target_user: discord.Member | discord.User,
        original_msg: discord.Message,
        target_channel: discord.TextChannel | None,
        reason: str,
    ) -> discord.Embed:
        embed = discord.Embed(title="⚠️ معلومات التحذير", color=discord.Color.red(), timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="المُحذِر:", value=interaction.user.mention, inline=True)
        embed.add_field(name="المُحذَّر:", value=target_user.mention, inline=True)
        embed.add_field(name="السبب:", value=reason, inline=False)
        if target_channel:
            embed.add_field(name="القناة:", value=target_channel.mention, inline=True)
        embed.add_field(name="نص المنشور:", value=original_msg.content[:1000] if original_msg.content else "بدون نص", inline=False)
        if original_msg.attachments:
            embed.set_image(url=original_msg.attachments[0].url)
        return embed

    async def handle_warning_submit(
        self,
        interaction: discord.Interaction,
        target_user: discord.Member | discord.User,
        original_msg: discord.Message,
        target_channel: discord.TextChannel | None,
        reason: str,
    ) -> None:
        """Persist a moderator warning submitted from WarnReasonModal."""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild or not self.warn_log_channel_id:
            await interaction.followup.send("❌ لم يتم تحديد قناة للتحذيرات!", ephemeral=True)
            return
        log_channel = interaction.guild.get_channel(self.warn_log_channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.followup.send("❌ قناة التحذيرات غير موجودة.", ephemeral=True)
            return

        db = load_json(WARNINGS_DB, {})
        user_id = str(target_user.id)
        db.setdefault(user_id, {"count": 0, "reasons": []})
        db[user_id]["count"] = int(db[user_id].get("count", 0)) + 1
        db[user_id].setdefault("reasons", []).append(reason)
        save_json(WARNINGS_DB, db)

        await log_channel.send(embed=self._warning_embed(interaction, target_user, original_msg, target_channel, reason))
        await interaction.followup.send(f"✅ تم تسجيل التحذير في <#{self.warn_log_channel_id}>", ephemeral=True)
        if db[user_id]["count"] >= int(self.mod_config.get("max_warns", 3)):
            await interaction.followup.send(
                f"🚨 **تنبيه!** {target_user.mention} وصل للحد الأقصى! اختر عقوبة:",
                view=PunishmentView(target_user),
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Relay configured sales channels through a webhook with moderation buttons."""
        if not message.guild or message.author.bot or message.webhook_id is not None:
            return
        if not isinstance(message.channel, discord.TextChannel) or message.channel.id not in self.allowed_channels:
            return

        text = normalize_sales_text(message.content)
        files = [await attachment.to_file() for attachment in message.attachments]
        try:
            webhook = await self._get_or_create_webhook(message.channel)
            await webhook.send(
                content=text or None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                view=MainSalesView(self, message.author.display_name, message.author.id, message.channel.id, message),
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await message.delete()
        except discord.HTTPException:
            LOGGER.exception("Failed to relay sales message %s in channel %s", message.id, message.channel.id)
            fallback = text or "تعذر إعادة نشر رسالة المبيعات عبر الويب هوك."
            await message.channel.send(fallback, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="set_log_channel")
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the warning log channel."""
        self.warn_log_channel_id = channel.id
        save_list(LOG_CHANNEL_FILE, [channel.id])
        await ctx.send(f"✅ تم تحديد قناة التحذيرات: {channel.mention}")

    @commands.command(name="add_channel")
    @commands.has_permissions(administrator=True)
    async def add_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Enable sales relay in a channel."""
        if channel.id in self.allowed_channels:
            await ctx.send("⚠️ القناة مضافة مسبقاً.")
            return
        self.allowed_channels.append(channel.id)
        save_list(CHANNELS_FILE, self.allowed_channels)
        await ctx.send(f"✅ تمت إضافة {channel.mention} لنظام المبيعات.")

    @commands.command(name="remove_channel")
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Disable sales relay in a channel."""
        if channel.id not in self.allowed_channels:
            await ctx.send("⚠️ القناة ليست في القائمة.")
            return
        self.allowed_channels.remove(channel.id)
        save_list(CHANNELS_FILE, self.allowed_channels)
        await ctx.send(f"❌ تم حذف {channel.mention}")

    @commands.command(name="warn_stats")
    @commands.has_permissions(administrator=True)
    async def warn_stats(self, ctx: commands.Context) -> None:
        """Show warning counts for all warned users."""
        db = load_json(WARNINGS_DB, {})
        if not db:
            await ctx.send("❌ لا يوجد أي تحذيرات مسجلة.")
            return
        embed = discord.Embed(title="📊 إحصائيات التحذيرات", color=discord.Color.gold())
        for user_id, info in list(db.items())[:25]:
            embed.add_field(name=f"ID: {user_id}", value=f"تحذيرات: {info.get('count', 0)}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="user_warns")
    @commands.has_permissions(administrator=True)
    async def user_warns(self, ctx: commands.Context, user: discord.User) -> None:
        """Show warning reasons for a single user."""
        db = load_json(WARNINGS_DB, {})
        info = db.get(str(user.id))
        if not info:
            await ctx.send(f"✅ {user.display_name} ليس لديه تحذيرات.")
            return
        embed = discord.Embed(title=f"📜 سجل: {user.display_name}", color=discord.Color.orange())
        embed.add_field(name="العدد:", value=str(info.get("count", 0)), inline=True)
        embed.add_field(name="الأسباب:", value="\n".join(info.get("reasons", []))[:1024] or "لا توجد أسباب", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="set_auto_mod")
    @commands.has_permissions(administrator=True)
    async def set_auto_mod(self, ctx: commands.Context, max_warns: int, action: str) -> None:
        """Configure automatic moderation threshold and action label."""
        if max_warns < 1:
            await ctx.send("❌ عدد التحذيرات يجب أن يكون 1 أو أكثر.")
            return
        action = action.lower()
        if action not in {"timeout", "kick", "ban"}:
            await ctx.send("❌ العقوبة يجب أن تكون: timeout أو kick أو ban.")
            return
        self.mod_config = {"max_warns": max_warns, "action": action}
        save_json(CONFIG_FILE, self.mod_config)
        await ctx.send(f"✅ تم ضبط النظام: العقوبة هي `{action}` عند `{max_warns}` تحذيرات.")


async def setup(bot: commands.Bot) -> None:
    """Load the sales moderation cog."""
    await bot.add_cog(SalesModerationCog(bot))
