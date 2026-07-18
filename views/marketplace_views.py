"""Discord UI for secure marketplace listings and scam reports."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from database.marketplace_database import MarketplaceListing
from utils.embed_factory import ERROR_COLOR, SUCCESS_COLOR, make_embed

if TYPE_CHECKING:
    from cogs.marketplace import MarketplaceCog


def listing_embed(listing: MarketplaceListing, seller: discord.abc.User | None = None) -> discord.Embed:
    """Build a marketplace listing embed."""
    seller_text = seller.mention if seller else f"`{listing.seller_id}`"
    embed = discord.Embed(title=f"🔐 {listing.title}", description=listing.description, color=discord.Color.blurple())
    embed.add_field(name="Seller", value=f"{listing.seller_name}\n{seller_text}", inline=True)
    embed.add_field(name="Price", value=listing.price, inline=True)
    embed.add_field(name="Category", value=listing.category, inline=True)
    embed.add_field(name="Listing ID", value=f"`{listing.id}`", inline=True)
    embed.add_field(name="Status", value=listing.status, inline=True)
    embed.add_field(name="Created", value=listing.created_at, inline=True)
    if listing.channel_id:
        embed.add_field(name="Related Channel", value=f"<#{listing.channel_id}>", inline=False)
    if listing.evidence:
        embed.add_field(name="Evidence", value=listing.evidence[:1024], inline=False)
    if listing.image_url:
        embed.set_image(url=listing.image_url)
    return embed


class SellerWarningModal(discord.ui.Modal, title="تحذير البائع"):
    """Collect an administrator warning reason."""

    reason = discord.ui.TextInput(label="سبب التحذير", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    def __init__(self, cog: "MarketplaceCog", listing: MarketplaceListing) -> None:
        super().__init__()
        self.cog = cog
        self.listing = listing

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.warn_seller(interaction, self.listing, str(self.reason.value))


class MarketplaceListingView(discord.ui.View):
    """Buttons displayed below each marketplace listing."""

    def __init__(self, cog: "MarketplaceCog", listing_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.listing_id = listing_id

    async def _listing(self, interaction: discord.Interaction) -> MarketplaceListing | None:
        if not interaction.guild:
            return None
        listing = await self.cog.database.get_listing(interaction.guild.id, self.listing_id)
        if not listing:
            await interaction.response.send_message(embed=make_embed("Not found", "This listing no longer exists.", color=ERROR_COLOR), ephemeral=True)
        return listing

    @discord.ui.button(label="تواصل مع البائع", style=discord.ButtonStyle.primary, custom_id="marketplace_contact_seller")
    async def contact_seller(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        listing = await self._listing(interaction)
        if not listing:
            return
        await self.cog.contact_seller(interaction, listing)

    @discord.ui.button(label="View Profile", style=discord.ButtonStyle.secondary, custom_id="marketplace_view_profile")
    async def view_profile(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        listing = await self._listing(interaction)
        if not listing:
            return
        await self.cog.show_seller_profile(interaction, listing)

    @discord.ui.button(label="تحذير البائع", style=discord.ButtonStyle.danger, custom_id="marketplace_warn_seller")
    async def warn_seller(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        listing = await self._listing(interaction)
        if not listing:
            return
        permissions = getattr(interaction.user, "guild_permissions", None)
        if not permissions or not permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر للمسؤولين فقط.", ephemeral=True)
            return
        await interaction.response.send_modal(SellerWarningModal(self.cog, listing))


class ScamReportModal(discord.ui.Modal, title="Secure Scam Report"):
    """Collect a scam report."""

    accused = discord.ui.TextInput(label="الشخص المُبلغ عنه / ID", required=True, max_length=120)
    details = discord.ui.TextInput(label="التفاصيل", style=discord.TextStyle.paragraph, required=True, max_length=2000)
    amount = discord.ui.TextInput(label="المبلغ إن وجد", required=False, max_length=100)
    evidence = discord.ui.TextInput(label="روابط الأدلة أو الصور", required=False, style=discord.TextStyle.paragraph, max_length=1500)

    def __init__(self, cog: "MarketplaceCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.create_scam_report(interaction, str(self.accused.value), str(self.details.value), str(self.amount.value) or None, str(self.evidence.value) or None)
