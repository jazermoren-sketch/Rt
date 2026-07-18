"""Secure marketplace, seller listings, privacy relay, and scam reports."""
from __future__ import annotations

import datetime as dt
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from database.marketplace_database import MarketplaceDatabase, MarketplaceListing, ScamReportRecord
from utils.embed_factory import ERROR_COLOR, SUCCESS_COLOR, make_embed
from utils.permissions import admin_only
from utils.webhook_privacy import relay_private_message
from views.marketplace_views import MarketplaceListingView, ScamReportModal, listing_embed

LOGGER = logging.getLogger(__name__)
REPORT_STATUSES = {"Pending", "Under Review", "Confirmed", "Rejected"}


class MarketplaceCog(commands.Cog):
    """Secure marketplace product listings and scam-protection workflows."""

    marketplace = app_commands.Group(name="marketplace", description="Secure marketplace commands")
    marketplace_admin = app_commands.Group(name="marketplace_admin", description="Marketplace admin settings")
    scam = app_commands.Group(name="scam", description="Secure scam report commands")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = MarketplaceDatabase()

    async def cog_load(self) -> None:
        await self.database.initialize()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Apply webhook privacy relay in configured channels without loops."""
        if not message.guild or message.author.bot or message.webhook_id:
            return
        settings = await self.database.get_settings(message.guild.id)
        if message.channel.id in settings.get("privacy_channels", []):
            try:
                await relay_private_message(message, transform_text=True)
            except discord.HTTPException:
                LOGGER.exception("Marketplace privacy relay failed in channel %s", message.channel.id)

    def _is_creation_allowed(self, channel_id: int, settings: dict) -> bool:
        allowed = settings.get("product_creation_channels", [])
        return not allowed or channel_id in allowed

    async def _log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        settings = await self.database.get_settings(guild.id)
        channel_id = settings.get("logs_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def _publish_listing(self, guild: discord.Guild, listing: MarketplaceListing) -> bool:
        settings = await self.database.get_settings(guild.id)
        channel_id = settings.get("marketplace_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return False
        seller = guild.get_member(listing.seller_id) or self.bot.get_user(listing.seller_id)
        await channel.send(embed=listing_embed(listing, seller), view=MarketplaceListingView(self, listing.id), allowed_mentions=discord.AllowedMentions.none())
        return True

    async def contact_seller(self, interaction: discord.Interaction, listing: MarketplaceListing) -> None:
        """Open a controlled contact path with the seller."""
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        seller = interaction.guild.get_member(listing.seller_id) or self.bot.get_user(listing.seller_id)
        if not seller:
            await interaction.followup.send(embed=make_embed("Seller unavailable", "لا يمكن العثور على البائع حاليًا.", color=ERROR_COLOR), ephemeral=True)
            return
        try:
            await seller.send(
                embed=make_embed(
                    "Marketplace contact request",
                    f"{interaction.user.mention} wants to contact you about **{listing.title}** (`#{listing.id}`).\nServer: **{interaction.guild.name}**",
                    color=SUCCESS_COLOR,
                )
            )
        except discord.HTTPException:
            await interaction.followup.send(embed=make_embed("DM blocked", f"لا يمكن إرسال DM للبائع. يمكنك التواصل معه عبر mention منظم: {seller.mention}", color=ERROR_COLOR), ephemeral=True)
            return
        await interaction.followup.send(embed=make_embed("Contact sent", "تم إرسال طلب التواصل إلى البائع عبر DM.", color=SUCCESS_COLOR), ephemeral=True)

    async def show_seller_profile(self, interaction: discord.Interaction, listing: MarketplaceListing) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        member = interaction.guild.get_member(listing.seller_id)
        user = member or self.bot.get_user(listing.seller_id)
        products = await self.database.list_listings(interaction.guild.id, active_only=False, seller_id=listing.seller_id)
        warnings = await self.database.warning_count(interaction.guild.id, listing.seller_id)
        embed = discord.Embed(title="Seller Profile", color=discord.Color.blurple(), timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Username", value=str(user) if user else listing.seller_name, inline=True)
        embed.add_field(name="User ID", value=f"`{listing.seller_id}`", inline=True)
        if user:
            embed.add_field(name="Account Created", value=discord.utils.format_dt(user.created_at, style="R"), inline=True)
        if member and member.joined_at:
            embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, style="R"), inline=True)
        embed.add_field(name="Products", value=str(len(products)), inline=True)
        embed.add_field(name="Marketplace Warnings", value=str(warnings), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def warn_seller(self, interaction: discord.Interaction, listing: MarketplaceListing, reason: str) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        permissions = getattr(interaction.user, "guild_permissions", None)
        if not permissions or not permissions.administrator:
            await interaction.followup.send("❌ هذا الإجراء للمسؤولين فقط.", ephemeral=True)
            return
        warning_id = await self.database.add_warning(interaction.guild.id, listing.seller_id, interaction.user.id, listing.id, reason)
        seller = interaction.guild.get_member(listing.seller_id) or self.bot.get_user(listing.seller_id)
        if seller:
            try:
                await seller.send(embed=make_embed("Marketplace Warning", f"تم تحذيرك بخصوص **{listing.title}**.\nالسبب: {reason}", color=ERROR_COLOR))
            except discord.HTTPException:
                pass
        log = make_embed("Seller warned", f"Warning ID: `{warning_id}`\nSeller: `{listing.seller_id}`\nListing: `{listing.id}`\nReason: {reason}", color=ERROR_COLOR)
        await self._log(interaction.guild, log)
        await interaction.followup.send(embed=make_embed("Warning saved", f"تم تسجيل التحذير رقم `{warning_id}`.", color=SUCCESS_COLOR), ephemeral=True)

    def _report_embed(self, report: ScamReportRecord, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(title=f"🚨 Scam Report #{report.id}", description=report.details, color=discord.Color.orange(), timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Reporter", value=f"<@{report.reporter_id}>\n`{report.reporter_id}`", inline=True)
        embed.add_field(name="Accused", value=f"{report.accused_text}\n`{report.accused_id or 'unknown'}`", inline=True)
        embed.add_field(name="Amount", value=report.amount or "غير محدد", inline=True)
        embed.add_field(name="Status", value=report.status, inline=True)
        embed.add_field(name="Server", value=f"{guild.name}\n`{guild.id}`", inline=False)
        if report.evidence:
            embed.add_field(name="Evidence", value=report.evidence[:1024], inline=False)
        return embed

    async def create_scam_report(self, interaction: discord.Interaction, accused: str, details: str, amount: str | None, evidence: str | None) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        accused_id = int(match.group(1)) if (match := re.search(r"(\d{15,25})", accused)) else None
        report = await self.database.create_report(guild_id=interaction.guild.id, reporter_id=interaction.user.id, accused_id=accused_id, accused_text=accused, details=details, amount=amount, evidence=evidence)
        settings = await self.database.get_settings(interaction.guild.id)
        channel = interaction.guild.get_channel(settings.get("scam_reports_channel_id")) if settings.get("scam_reports_channel_id") else None
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=self._report_embed(report, interaction.guild), allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(embed=make_embed("Report submitted", f"تم تسجيل البلاغ برقم `{report.id}` وحالته `{report.status}`.", color=SUCCESS_COLOR), ephemeral=True)

    @marketplace.command(name="create", description="Create and publish a secure marketplace listing")
    async def create_listing(self, interaction: discord.Interaction, title: str, category: str, description: str, price: str, evidence: str | None = None, image_url: str | None = None, channel: discord.TextChannel | None = None) -> None:
        if not interaction.guild or not interaction.channel:
            return
        await interaction.response.defer(ephemeral=True)
        settings = await self.database.get_settings(interaction.guild.id)
        if not self._is_creation_allowed(interaction.channel.id, settings):
            await interaction.followup.send(embed=make_embed("Not allowed", "لا يمكن إنشاء المنتجات من هذه القناة.", color=ERROR_COLOR), ephemeral=True)
            return
        listing = await self.database.create_listing(guild_id=interaction.guild.id, seller_id=interaction.user.id, seller_name=str(interaction.user), title=title, category=category, description=description, price=price, channel_id=channel.id if channel else None, evidence=evidence, image_url=image_url)
        published = await self._publish_listing(interaction.guild, listing)
        await interaction.followup.send(embed=make_embed("Listing created", f"Listing ID: `{listing.id}`\nPublished: `{published}`", color=SUCCESS_COLOR), ephemeral=True)

    @marketplace.command(name="browse", description="Browse active marketplace listings")
    async def browse(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        listings = await self.database.list_listings(interaction.guild.id, active_only=True)
        if not listings:
            await interaction.followup.send(embed=make_embed("Marketplace", "لا توجد عروض نشطة حاليًا."), ephemeral=True)
            return
        for listing in listings[:5]:
            seller = interaction.guild.get_member(listing.seller_id) or self.bot.get_user(listing.seller_id)
            await interaction.followup.send(embed=listing_embed(listing, seller), view=MarketplaceListingView(self, listing.id), ephemeral=True)

    @marketplace.command(name="edit", description="Edit one of your marketplace listings")
    async def edit_listing(self, interaction: discord.Interaction, listing_id: int, title: str | None = None, category: str | None = None, description: str | None = None, price: str | None = None, evidence: str | None = None, image_url: str | None = None, status: str | None = None) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        listing = await self.database.get_listing(interaction.guild.id, listing_id)
        is_admin = bool(getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator)
        if not listing or (listing.seller_id != interaction.user.id and not is_admin):
            await interaction.followup.send(embed=make_embed("Not allowed", "لا يمكنك تعديل هذا العرض.", color=ERROR_COLOR), ephemeral=True)
            return
        listing = await self.database.update_listing(interaction.guild.id, listing_id, title=title, category=category, description=description, price=price, evidence=evidence, image_url=image_url, status=status)
        await interaction.followup.send(embed=listing_embed(listing, interaction.user), ephemeral=True)  # type: ignore[arg-type]

    @marketplace.command(name="delete", description="Close one of your marketplace listings")
    async def delete_listing(self, interaction: discord.Interaction, listing_id: int) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        listing = await self.database.get_listing(interaction.guild.id, listing_id)
        is_admin = bool(getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator)
        if not listing or (listing.seller_id != interaction.user.id and not is_admin):
            await interaction.followup.send(embed=make_embed("Not allowed", "لا يمكنك حذف هذا العرض.", color=ERROR_COLOR), ephemeral=True)
            return
        updated = await self.database.update_listing(interaction.guild.id, listing_id, status="Deleted")
        await interaction.followup.send(embed=make_embed("Listing deleted", f"Listing `{updated.id if updated else listing_id}` was closed.", color=SUCCESS_COLOR), ephemeral=True)

    @scam.command(name="report", description="Submit a structured scam report")
    async def scam_report(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ScamReportModal(self))

    @scam.command(name="set_status", description="Update scam report review status")
    @admin_only()
    async def set_report_status(self, interaction: discord.Interaction, report_id: int, status: str) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if status not in REPORT_STATUSES:
            await interaction.followup.send(embed=make_embed("Invalid status", ", ".join(sorted(REPORT_STATUSES)), color=ERROR_COLOR), ephemeral=True)
            return
        report = await self.database.update_report_status(interaction.guild.id, report_id, status)
        if not report:
            await interaction.followup.send(embed=make_embed("Not found", "Report not found.", color=ERROR_COLOR), ephemeral=True)
            return
        await interaction.followup.send(embed=self._report_embed(report, interaction.guild), ephemeral=True)

    @set_report_status.autocomplete("status")
    async def status_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=s, value=s) for s in sorted(REPORT_STATUSES) if current.lower() in s.lower()]

    @marketplace_admin.command(name="set_channel", description="Set marketplace/scam/log channel")
    @admin_only()
    async def set_channel(self, interaction: discord.Interaction, setting: str, channel: discord.TextChannel) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        mapping = {"marketplace": "marketplace_channel_id", "scam_reports": "scam_reports_channel_id", "logs": "logs_channel_id"}
        if setting not in mapping:
            await interaction.followup.send(embed=make_embed("Invalid setting", "Use marketplace, scam_reports, or logs.", color=ERROR_COLOR), ephemeral=True)
            return
        await self.database.set_channel(interaction.guild.id, mapping[setting], channel.id)
        await interaction.followup.send(embed=make_embed("Setting updated", f"{setting} channel set to {channel.mention}.", color=SUCCESS_COLOR), ephemeral=True)

    @set_channel.autocomplete("setting")
    async def setting_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        values = ["marketplace", "scam_reports", "logs"]
        return [app_commands.Choice(name=v, value=v) for v in values if current.lower() in v]

    @marketplace_admin.command(name="toggle_channel", description="Enable/disable product creation or privacy in a channel")
    @admin_only()
    async def toggle_channel(self, interaction: discord.Interaction, setting: str, channel: discord.TextChannel, enabled: bool = True) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        mapping = {"creation": "product_creation_channels", "privacy": "privacy_channels"}
        if setting not in mapping:
            await interaction.followup.send(embed=make_embed("Invalid setting", "Use creation or privacy.", color=ERROR_COLOR), ephemeral=True)
            return
        values = await self.database.toggle_list_channel(interaction.guild.id, mapping[setting], channel.id, enabled)
        await interaction.followup.send(embed=make_embed("Setting updated", f"{setting}: {', '.join(f'<#{cid}>' for cid in values) or 'none'}", color=SUCCESS_COLOR), ephemeral=True)

    @toggle_channel.autocomplete("setting")
    async def toggle_setting_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        values = ["creation", "privacy"]
        return [app_commands.Choice(name=v, value=v) for v in values if current.lower() in v]

    @marketplace_admin.command(name="settings", description="Show secure marketplace settings")
    @admin_only()
    async def settings(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        settings = await self.database.get_settings(interaction.guild.id)
        embed = make_embed("Marketplace Settings")
        embed.add_field(name="Marketplace", value=f"<#{settings['marketplace_channel_id']}>" if settings.get("marketplace_channel_id") else "None", inline=True)
        embed.add_field(name="Scam Reports", value=f"<#{settings['scam_reports_channel_id']}>" if settings.get("scam_reports_channel_id") else "None", inline=True)
        embed.add_field(name="Logs", value=f"<#{settings['logs_channel_id']}>" if settings.get("logs_channel_id") else "None", inline=True)
        embed.add_field(name="Creation Channels", value=", ".join(f"<#{cid}>" for cid in settings.get("product_creation_channels", [])) or "Any channel", inline=False)
        embed.add_field(name="Privacy Channels", value=", ".join(f"<#{cid}>" for cid in settings.get("privacy_channels", [])) or "None", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load secure marketplace cog."""
    await bot.add_cog(MarketplaceCog(bot))
