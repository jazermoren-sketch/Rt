"""Discord UI components for the shop system."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from database.sales_database import Product

if TYPE_CHECKING:
    from cogs.sales import SalesCog


PRODUCTS_PER_PAGE = 24


def product_embed(product: Product) -> discord.Embed:
    """Build a professional product details embed."""
    embed = discord.Embed(
        title=f"🛒 {product.name}",
        description=product.description or "لا يوجد وصف.",
        color=discord.Color.green() if product.active and product.stock > 0 else discord.Color.dark_grey(),
    )
    embed.add_field(name="Product ID", value=f"`{product.id}`", inline=True)
    embed.add_field(name="السعر", value=f"{product.price} credits", inline=True)
    embed.add_field(name="المخزون", value=str(product.stock), inline=True)
    embed.add_field(name="الحالة", value="متاح" if product.active else "مخفي", inline=True)
    if product.image_url:
        embed.set_image(url=product.image_url)
    return embed


class ProductSelect(discord.ui.Select):
    """Select menu for products on the current page."""

    def __init__(self, view: "ShopView") -> None:
        self.shop_view = view
        page_products = view.current_products
        options = [
            discord.SelectOption(
                label=product.name[:100],
                value=str(product.id),
                description=f"{product.price} credits • stock: {product.stock}"[:100],
            )
            for product in page_products
        ] or [discord.SelectOption(label="لا توجد منتجات", value="none", description="لا توجد منتجات متاحة")]
        super().__init__(placeholder="اختر منتجًا لعرض التفاصيل", min_values=1, max_values=1, options=options, disabled=not page_products)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "none":
            await interaction.response.send_message("لا توجد منتجات متاحة.", ephemeral=True)
            return
        await self.shop_view.show_product(interaction, int(self.values[0]))


class ProductDetailView(discord.ui.View):
    """Product detail view with a purchase button."""

    def __init__(self, cog: "SalesCog", guild_id: int, product_id: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.product_id = product_id

    @discord.ui.button(label="شراء", style=discord.ButtonStyle.success, emoji="🛒")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_purchase(interaction, self.product_id, quantity=1)


class ShopView(discord.ui.View):
    """Paginated shop browser with select menus."""

    def __init__(self, cog: "SalesCog", guild_id: int, products: list[Product], page: int = 0) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.products = products
        self.page = page
        self.refresh_items()

    @property
    def max_page(self) -> int:
        return max((len(self.products) - 1) // PRODUCTS_PER_PAGE, 0)

    @property
    def current_products(self) -> list[Product]:
        start = self.page * PRODUCTS_PER_PAGE
        return self.products[start:start + PRODUCTS_PER_PAGE]

    def refresh_items(self) -> None:
        self.clear_items()
        self.add_item(ProductSelect(self))
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= self.max_page
        self.add_item(self.previous_page)
        self.add_item(self.next_page)
        self.add_item(self.refresh)

    async def show_product(self, interaction: discord.Interaction, product_id: int) -> None:
        product = await self.cog.database.get_product(self.guild_id, product_id)
        if not product or not product.active:
            await interaction.response.send_message("❌ المنتج غير موجود أو غير متاح.", ephemeral=True)
            return
        await interaction.response.send_message(embed=product_embed(product), view=ProductDetailView(self.cog, self.guild_id, product.id), ephemeral=True)

    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(self.page - 1, 0)
        self.refresh_items()
        await interaction.response.edit_message(embed=self.cog.shop_embed(self.products, self.page), view=self)

    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.page + 1, self.max_page)
        self.refresh_items()
        await interaction.response.edit_message(embed=self.cog.shop_embed(self.products, self.page), view=self)

    @discord.ui.button(label="تحديث", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        products = await self.cog.database.list_products(self.guild_id, active_only=True)
        self.products = products
        self.page = min(self.page, self.max_page)
        self.refresh_items()
        await interaction.response.edit_message(embed=self.cog.shop_embed(products, self.page), view=self)
