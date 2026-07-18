"""Shop and sales system cog."""
from __future__ import annotations

import datetime as dt
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.sales_database import Product, Purchase, SalesDatabase
from utils.economy import EconomyService
from utils.embed_factory import ERROR_COLOR, SUCCESS_COLOR, make_embed
from utils.permissions import admin_only
from views.shop_views import ShopView, product_embed

LOGGER = logging.getLogger(__name__)


class SalesCog(commands.Cog):
    """SQLite-backed shop, purchases, and sales logging."""

    shop = app_commands.Group(name="shop", description="Browse and buy shop products")
    sales = app_commands.Group(name="sales", description="Admin sales and shop management")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = SalesDatabase()
        self.economy = EconomyService(self.database)

    async def cog_load(self) -> None:
        await self.database.initialize()

    def shop_embed(self, products: list[Product], page: int = 0) -> discord.Embed:
        """Build the public shop listing embed."""
        embed = discord.Embed(
            title="🛍️ Server Shop",
            description="اختر منتجًا من القائمة لعرض التفاصيل والشراء.",
            color=discord.Color.blurple(),
            timestamp=dt.datetime.now(dt.UTC),
        )
        if not products:
            embed.description = "لا توجد منتجات متاحة حاليًا."
            return embed
        start = page * 24
        for product in products[start:start + 24]:
            status = "✅" if product.active and product.stock > 0 else "❌"
            embed.add_field(
                name=f"{status} {product.name}",
                value=f"السعر: `{product.price}` credits\nالمخزون: `{product.stock}`\nID: `{product.id}`",
                inline=True,
            )
        embed.set_footer(text=f"Page {page + 1}/{max((len(products) - 1) // 24 + 1, 1)}")
        return embed

    async def _send_sales_log(self, guild: discord.Guild, buyer: discord.abc.User, purchase: Purchase) -> None:
        """Send a structured purchase log to the configured sales log channel."""
        channel_id = await self.database.get_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title="🧾 عملية شراء جديدة", color=discord.Color.gold(), timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="المشتري", value=f"{buyer.mention}\n`{buyer.id}`", inline=True)
        embed.add_field(name="المنتج", value=f"{purchase.product_name}\nID: `{purchase.product_id}`", inline=True)
        embed.add_field(name="السعر", value=str(purchase.total_price), inline=True)
        embed.add_field(name="الكمية", value=str(purchase.quantity), inline=True)
        embed.add_field(name="السيرفر", value=f"{guild.name}\n`{guild.id}`", inline=False)
        embed.set_footer(text=f"Purchase ID: {purchase.id}")
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def handle_purchase(self, interaction: discord.Interaction, product_id: int, *, quantity: int = 1) -> None:
        """Perform an atomic purchase and send confirmation/logs."""
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        ok, message, purchase, balance = await self.database.purchase(interaction.guild.id, interaction.user.id, product_id, quantity)
        if not ok or not purchase:
            await interaction.followup.send(embed=make_embed("Purchase failed", message, color=ERROR_COLOR), ephemeral=True)
            return
        await self._send_sales_log(interaction.guild, interaction.user, purchase)
        embed = make_embed("Purchase complete", f"اشتريت **{purchase.product_name}** مقابل `{purchase.total_price}` credits.\nرصيدك الحالي: `{balance}`.", color=SUCCESS_COLOR)
        embed.set_footer(text=f"Purchase ID: {purchase.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @shop.command(name="open", description="Open the server shop")
    async def open_shop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        products = await self.database.list_products(interaction.guild.id, active_only=True)
        await interaction.followup.send(embed=self.shop_embed(products), view=ShopView(self, interaction.guild.id, products), ephemeral=True)

    @shop.command(name="balance", description="Show your shop balance")
    async def balance(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        balance = await self.economy.get_balance(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(embed=make_embed("Balance", f"رصيدك: `{balance}` credits.", color=SUCCESS_COLOR), ephemeral=True)

    @sales.command(name="add_product", description="Add a shop product")
    @admin_only()
    async def add_product(self, interaction: discord.Interaction, name: str, description: str, price: int, stock: int, image_url: str | None = None) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if price < 0 or stock < 0:
            await interaction.followup.send(embed=make_embed("Invalid product", "Price and stock must be zero or greater.", color=ERROR_COLOR), ephemeral=True)
            return
        product = await self.database.add_product(interaction.guild.id, name, description, price, stock, image_url)
        await interaction.followup.send(embed=product_embed(product), ephemeral=True)

    async def _edit_product_response(
        self,
        interaction: discord.Interaction,
        product_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        price: int | None = None,
        stock: int | None = None,
        image_url: str | None = None,
        active: bool | None = None,
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if (price is not None and price < 0) or (stock is not None and stock < 0):
            await interaction.followup.send(embed=make_embed("Invalid product", "Price and stock must be zero or greater.", color=ERROR_COLOR), ephemeral=True)
            return
        product = await self.database.update_product(interaction.guild.id, product_id, name=name, description=description, price=price, stock=stock, image_url=image_url, active=active)
        if not product:
            await interaction.followup.send(embed=make_embed("Not found", "Product was not found.", color=ERROR_COLOR), ephemeral=True)
            return
        await interaction.followup.send(embed=product_embed(product), ephemeral=True)

    @sales.command(name="edit_product", description="Edit product name, description, image, stock, price, or active state")
    @admin_only()
    async def edit_product(
        self,
        interaction: discord.Interaction,
        product_id: int,
        name: str | None = None,
        description: str | None = None,
        price: int | None = None,
        stock: int | None = None,
        image_url: str | None = None,
        active: bool | None = None,
    ) -> None:
        await self._edit_product_response(interaction, product_id, name=name, description=description, price=price, stock=stock, image_url=image_url, active=active)

    @sales.command(name="set_price", description="Update a product price")
    @admin_only()
    async def set_price(self, interaction: discord.Interaction, product_id: int, price: int) -> None:
        await self._edit_product_response(interaction, product_id, price=price)

    @sales.command(name="set_description", description="Update a product description")
    @admin_only()
    async def set_description(self, interaction: discord.Interaction, product_id: int, description: str) -> None:
        await self._edit_product_response(interaction, product_id, description=description)

    @sales.command(name="add_stock", description="Add stock to a product")
    @admin_only()
    async def add_stock(self, interaction: discord.Interaction, product_id: int, amount: int) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if amount < 1:
            await interaction.followup.send(embed=make_embed("Invalid stock", "Amount must be at least 1.", color=ERROR_COLOR), ephemeral=True)
            return
        product = await self.database.add_stock(interaction.guild.id, product_id, amount)
        if not product:
            await interaction.followup.send(embed=make_embed("Not found", "Product was not found.", color=ERROR_COLOR), ephemeral=True)
            return
        await interaction.followup.send(embed=product_embed(product), ephemeral=True)

    @sales.command(name="remove_product", description="Deactivate a product")
    @admin_only()
    async def remove_product(self, interaction: discord.Interaction, product_id: int) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        product = await self.database.update_product(interaction.guild.id, product_id, active=False)
        title = "Product removed" if product else "Not found"
        await interaction.followup.send(embed=make_embed(title, f"Product ID `{product_id}`.", color=SUCCESS_COLOR if product else ERROR_COLOR), ephemeral=True)

    @sales.command(name="list_products", description="List all shop products")
    @admin_only()
    async def list_products(self, interaction: discord.Interaction, include_inactive: bool = True) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        products = await self.database.list_products(interaction.guild.id, active_only=not include_inactive)
        await interaction.followup.send(embed=self.shop_embed(products), ephemeral=True)

    @sales.command(name="publish_shop", description="Publish the shop in a channel")
    @admin_only()
    async def publish_shop(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        products = await self.database.list_products(interaction.guild.id, active_only=True)
        await channel.send(embed=self.shop_embed(products), view=ShopView(self, interaction.guild.id, products), allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(embed=make_embed("Shop published", f"Shop posted in {channel.mention}.", color=SUCCESS_COLOR), ephemeral=True)

    @sales.command(name="set_logs", description="Set the sales log channel")
    @admin_only()
    async def set_logs(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        await self.database.set_log_channel(interaction.guild.id, channel.id)
        await interaction.followup.send(embed=make_embed("Logs updated", f"Sales logs will be sent to {channel.mention}.", color=SUCCESS_COLOR), ephemeral=True)

    @sales.command(name="give_balance", description="Add shop credits to a user")
    @admin_only()
    async def give_balance(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        if amount == 0:
            await interaction.followup.send(embed=make_embed("Invalid amount", "Amount cannot be zero.", color=ERROR_COLOR), ephemeral=True)
            return
        balance = await self.economy.add_balance(interaction.guild.id, user.id, amount)
        await interaction.followup.send(embed=make_embed("Balance updated", f"{user.mention} balance is now `{balance}` credits.", color=SUCCESS_COLOR), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the shop/sales cog."""
    await bot.add_cog(SalesCog(bot))
