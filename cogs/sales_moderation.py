"""Existing sales relay and warning moderation features."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

CHANNELS_FILE = Path("channels.txt")
LOG_CHANNEL_FILE = Path("log_channel.txt")
WARNINGS_DB = Path("warnings_db.json")
CONFIG_FILE = Path("mod_config.json")

MAPPING = {
    "ح": "7", "ع": "3", "خ": "5", "ط": "6", "ص": "9", "ض": "d",
    "ق": "8", "ء": "2", "ؤ": "2", "ئ": "2", "أ": "1", "إ": "1", "آ": "1",
}


def load_list(path: Path) -> list[int]:
    """Load integer IDs from a newline-delimited text file."""
    if not path.exists():
        return []
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip().isdigit()]


def save_list(path: Path, data: list[int]) -> None:
    """Save integer IDs to a newline-delimited text file."""
    path.write_text("".join(f"{item}\n" for item in data), encoding="utf-8")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """Load JSON with a safe default."""
    if not path.exists():
        return default.copy()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default.copy()


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Save JSON data."""
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


class PunishmentView(discord.ui.View):
    """Moderator punishment buttons for users reaching warning limits."""

    def __init__(self, user: discord.Member | discord.User) -> None:
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Time Out", style=discord.ButtonStyle.secondary)
    async def timeout(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.user.timeout(dt.timedelta(minutes=60), reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم عمل Timeout لـ {self.user.mention}", ephemeral=True)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.user.kick(reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم طرد {self.user.mention}", ephemeral=True)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.user.ban(reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم حظر {self.user.mention}", ephemeral=True)


class WarnReasonModal(discord.ui.Modal, title="إرسال تحذير للمنشور"):
    """Collect a warning reason from a moderator."""

    reason = discord.ui.TextInput(label="سبب التحذير", style=discord.TextStyle.paragraph, placeholder="اكتب السبب هنا...", required=True)

    def __init__(self, cog: "SalesModerationCog", target_user: discord.Member | discord.User, original_msg: discord.Message, target_channel: discord.TextChannel | None) -> None:
        super().__init__()
        self.cog = cog
        self.target_user = target_user
        self.original_msg = original_msg
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild or not self.cog.warn_log_channel_id:
            await interaction.followup.send("❌ لم يتم تحديد قناة للتحذيرات!")
            return
        log_channel = interaction.guild.get_channel(self.cog.warn_log_channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.followup.send("❌ قناة التحذيرات غير موجودة.")
            return
        db = load_json(WARNINGS_DB, {})
        user_id = str(self.target_user.id)
        db.setdefault(user_id, {"count": 0, "reasons": []})
        db[user_id]["count"] += 1
        db[user_id]["reasons"].append(str(self.reason.value))
        save_json(WARNINGS_DB, db)

        embed = discord.Embed(title="⚠️ معلومات التحذير", color=discord.Color.red())
        embed.add_field(name="المُحذِر:", value=interaction.user.mention, inline=True)
        embed.add_field(name="المُحذَّر:", value=self.target_user.mention, inline=True)
        embed.add_field(name="السبب:", value=str(self.reason.value), inline=False)
        if self.target_channel:
            embed.add_field(name="القناة:", value=self.target_channel.mention, inline=True)
        embed.add_field(name="نص المنشور:", value=self.original_msg.content[:100] if self.original_msg.content else "بدون نص", inline=False)
        embed.set_footer(text=f"الوقت: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.original_msg.attachments:
            embed.set_image(url=self.original_msg.attachments[0].url)
        await log_channel.send(embed=embed)
        await interaction.followup.send(f"✅ تم تسجيل التحذير في <#{self.cog.warn_log_channel_id}>")
        if db[user_id]["count"] >= int(self.cog.mod_config.get("max_warns", 3)):
            await interaction.followup.send(f"🚨 **تنبيه!** {self.target_user.mention} وصل للحد الأقصى! اختر عقوبة:", view=PunishmentView(self.target_user), ephemeral=False)


class SellerDetailsView(discord.ui.View):
    """Seller detail buttons shown privately to users."""

    def __init__(self, cog: "SalesModerationCog", seller_name: str, seller_id: int, channel_id: int, original_msg: discord.Message) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.seller_name = seller_name
        self.seller_id = seller_id
        self.channel_id = channel_id
        self.original_msg = original_msg

    @discord.ui.button(label="View Profile", style=discord.ButtonStyle.secondary)
    async def view_profile(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(f"🔗 [اضغط هنا لزيارة الملف الشخصي](https://discord.com/users/{self.seller_id})", ephemeral=True)

    @discord.ui.button(label="تحذير البائع", style=discord.ButtonStyle.danger)
    async def warn_seller(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر للمشرفين فقط!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        await interaction.response.send_modal(WarnReasonModal(self.cog, self.original_msg.author, self.original_msg, channel if isinstance(channel, discord.TextChannel) else None))


class MainSalesView(discord.ui.View):
    """Public contact button for relayed sales posts."""

    def __init__(self, cog: "SalesModerationCog", seller_name: str, seller_id: int, channel_id: int, original_msg: discord.Message) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.seller_name = seller_name
        self.seller_id = seller_id
        self.channel_id = channel_id
        self.original_msg = original_msg

    @discord.ui.button(label="تواصل مع البائع", style=discord.ButtonStyle.primary)
    async def contact_seller(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = discord.Embed(title="تفاصيل البائع", color=discord.Color.blue())
        embed.add_field(name="البائع:", value=self.seller_name, inline=True)
        embed.add_field(name="الايدي:", value=f"`{self.seller_id}`", inline=True)
        embed.add_field(name="القناة:", value=f"<#{self.channel_id}>", inline=True)
        await interaction.response.send_message(embed=embed, view=SellerDetailsView(self.cog, self.seller_name, self.seller_id, self.channel_id, self.original_msg), ephemeral=True)


class SalesModerationCog(commands.Cog):
    """Existing sales relay and warning commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.allowed_channels = load_list(CHANNELS_FILE)
        log_channels = load_list(LOG_CHANNEL_FILE)
        self.warn_log_channel_id = log_channels[0] if log_channels else None
        self.mod_config = load_json(CONFIG_FILE, {"max_warns": 3, "action": "kick"})
        self.webhooks_cache: dict[int, discord.Webhook] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return
        if message.channel.id not in self.allowed_channels:
            return
        text = message.content
        for arabic, franko in MAPPING.items():
            text = text.replace(arabic, franko)
        try:
            if message.channel.id not in self.webhooks_cache:
                self.webhooks_cache[message.channel.id] = await message.channel.create_webhook(name=f"Sales_{message.channel.name}")
            webhook = self.webhooks_cache[message.channel.id]
            files = [await attachment.to_file() for attachment in message.attachments]
            await webhook.send(content=text or None, username=message.author.display_name, avatar_url=message.author.display_avatar.url, view=MainSalesView(self, message.author.display_name, message.author.id, message.channel.id, message), files=files)
            await message.delete()
        except discord.HTTPException:
            await message.channel.send(text)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        self.warn_log_channel_id = channel.id
        save_list(LOG_CHANNEL_FILE, [channel.id])
        await ctx.send(f"✅ تم تحديد قناة التحذيرات: {channel.mention}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def add_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        if channel.id not in self.allowed_channels:
            self.allowed_channels.append(channel.id)
            save_list(CHANNELS_FILE, self.allowed_channels)
            await ctx.send(f"✅ تمت إضافة {channel.mention} لنظام المبيعات.")
        else:
            await ctx.send("⚠️ القناة مضافة مسبقاً.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        if channel.id in self.allowed_channels:
            self.allowed_channels.remove(channel.id)
            save_list(CHANNELS_FILE, self.allowed_channels)
            await ctx.send(f"❌ تم حذف {channel.mention}")
        else:
            await ctx.send("⚠️ القناة ليست في القائمة.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def warn_stats(self, ctx: commands.Context) -> None:
        db = load_json(WARNINGS_DB, {})
        if not db:
            await ctx.send("❌ لا يوجد أي تحذيرات مسجلة.")
            return
        embed = discord.Embed(title="📊 إحصائيات التحذيرات", color=discord.Color.gold())
        for user_id, info in db.items():
            embed.add_field(name=f"ID: {user_id}", value=f"تحذيرات: {info['count']}", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def user_warns(self, ctx: commands.Context, user: discord.User) -> None:
        db = load_json(WARNINGS_DB, {})
        user_id = str(user.id)
        if user_id not in db:
            await ctx.send(f"✅ {user.display_name} ليس لديه تحذيرات.")
            return
        info = db[user_id]
        embed = discord.Embed(title=f"📜 سجل: {user.display_name}", color=discord.Color.orange())
        embed.add_field(name="العدد:", value=info["count"], inline=True)
        embed.add_field(name="الأسباب:", value="\n".join(info["reasons"]), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_auto_mod(self, ctx: commands.Context, max_warns: int, action: str) -> None:
        self.mod_config = {"max_warns": max_warns, "action": action.lower()}
        save_json(CONFIG_FILE, self.mod_config)
        await ctx.send(f"✅ تم ضبط النظام: العقوبة هي `{action}` عند `{max_warns}` تحذيرات.")


async def setup(bot: commands.Bot) -> None:
    """Load the sales/moderation cog."""
    await bot.add_cog(SalesModerationCog(bot))
