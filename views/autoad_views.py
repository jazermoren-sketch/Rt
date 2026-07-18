"""Discord UI views for Auto Advertisement management."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from utils.embed_factory import ERROR_COLOR, SUCCESS_COLOR, make_embed

if TYPE_CHECKING:
    from cogs.autoad import AutoAdCog


class AutoAdPreviewView(discord.ui.View):
    """Preview helper buttons for an advertisement."""

    def __init__(self, cog: "AutoAdCog", guild_id: int, ad_id: str) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.ad_id = ad_id

    @discord.ui.button(label="Send Test", style=discord.ButtonStyle.primary)
    async def send_test(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Send the previewed advertisement to the current channel."""
        if not interaction.channel:
            await interaction.response.send_message(embed=make_embed("No channel", "Unable to find the current channel.", color=ERROR_COLOR), ephemeral=True)
            return
        ok = await self.cog.send_specific_ad(interaction.channel, self.guild_id, self.ad_id, manual=True)
        await interaction.response.send_message(embed=make_embed("Sent" if ok else "Not found", "Preview advertisement test send complete.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_ad(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Delete the previewed advertisement."""
        ok = await self.cog.delete_ad(self.guild_id, self.ad_id)
        await interaction.response.send_message(embed=make_embed("Deleted" if ok else "Not found", f"Advertisement `{self.ad_id}`.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)
        if ok:
            for child in self.children:
                child.disabled = True  # type: ignore[attr-defined]
            if interaction.message:
                await interaction.message.edit(view=self)


class AutoAdModeSelect(discord.ui.Select):
    """Dropdown for choosing AutoAd dispatch mode."""

    def __init__(self, cog: "AutoAdCog", guild_id: int) -> None:
        self.cog = cog
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="Timer", value="timer", description="Send ads by interval"),
            discord.SelectOption(label="Rotate", value="rotate", description="Cycle through ads"),
            discord.SelectOption(label="Random", value="random", description="Choose ads randomly"),
            discord.SelectOption(label="Every Message", value="every_message", description="Send after every user message"),
            discord.SelectOption(label="Message Count", value="message_count", description="Send after N messages"),
        ]
        super().__init__(placeholder="Select AutoAd mode", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        config = await self.cog.manager.get_config(self.guild_id)
        config["mode"] = self.values[0]
        await self.cog.manager.save_config(self.guild_id, config)
        await interaction.response.send_message(embed=make_embed("Mode updated", f"Mode set to `{self.values[0]}`.", color=SUCCESS_COLOR), ephemeral=True)


class AutoAdModeSelectView(discord.ui.View):
    """View containing a mode dropdown."""

    def __init__(self, cog: "AutoAdCog", guild_id: int) -> None:
        super().__init__(timeout=180)
        self.add_item(AutoAdModeSelect(cog, guild_id))

AUTOAD_ALL_VALUE = "__all_autoads__"
AUTOADS_PER_PAGE = 24


class AutoAdEditModal(discord.ui.Modal, title="Edit AutoAd"):
    """Modal for editing a selected advertisement."""

    name = discord.ui.TextInput(label="Name", required=False, max_length=100)
    message = discord.ui.TextInput(label="Message", required=False, style=discord.TextStyle.paragraph, max_length=2000)
    image_url = discord.ui.TextInput(label="Image URL", required=False, max_length=500)
    embed_title = discord.ui.TextInput(label="Embed title", required=False, max_length=256)
    embed_description = discord.ui.TextInput(label="Embed description", required=False, style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, cog: "AutoAdCog", guild_id: int, ad: dict) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.ad_id = ad["id"]
        self.name.default = ad.get("name") or ""
        self.message.default = ad.get("message") or ""
        self.image_url.default = ad.get("image_url") or ""
        self.embed_title.default = ad.get("embed_title") or ""
        self.embed_description.default = ad.get("embed_description") or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        config = await self.cog.manager.get_config(self.guild_id)
        for ad in config.get("ads", []):
            if ad.get("id") == self.ad_id:
                ad["name"] = str(self.name.value) or ad.get("name")
                ad["message"] = str(self.message.value) or None
                ad["image_url"] = str(self.image_url.value) or None
                ad["embed_title"] = str(self.embed_title.value) or None
                ad["embed_description"] = str(self.embed_description.value) or None
                await self.cog.manager.save_config(self.guild_id, config)
                await interaction.followup.send(embed=make_embed("Advertisement updated", f"Updated `{ad['name']}`.", color=SUCCESS_COLOR), ephemeral=True)
                return
        await interaction.followup.send(embed=make_embed("Not found", "The selected advertisement no longer exists.", color=ERROR_COLOR), ephemeral=True)


class AutoAdConfirmAllView(discord.ui.View):
    """Confirmation view for bulk AutoAd actions."""

    def __init__(self, selector: "AutoAdSelectView") -> None:
        super().__init__(timeout=60)
        self.selector = selector

    @discord.ui.button(label="Confirm Manage All AutoAds", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.selector.run_bulk_action(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=make_embed("Cancelled", "Bulk AutoAd action cancelled."), view=None)


class AutoAdSelect(discord.ui.Select):
    """Select a single AutoAd or the explicit Manage All option."""

    def __init__(self, view: "AutoAdSelectView") -> None:
        self.selector_view = view
        page_ads = view.current_ads
        options = [
            discord.SelectOption(label="Manage All AutoAds", value=AUTOAD_ALL_VALUE, description="Requires confirmation before any bulk action."),
        ]
        options.extend(
            discord.SelectOption(
                label=str(ad.get("name") or "Untitled")[:100],
                value=str(ad.get("id")),
                description=f"ID: {ad.get('id')} • Sent: {ad.get('sent', 0)}"[:100],
            )
            for ad in page_ads
        )
        super().__init__(placeholder=view.placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selector_view.handle_selection(interaction, self.values[0])


class AutoAdSelectView(discord.ui.View):
    """Paginated AutoAd selection view for edit/delete/preview/send actions."""

    def __init__(self, cog: "AutoAdCog", guild_id: int, ads: list[dict], operation: str, page: int = 0, channel: discord.abc.Messageable | None = None) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.ads = ads
        self.operation = operation
        self.page = page
        self.channel = channel
        self.refresh_items()

    @property
    def placeholder(self) -> str:
        return f"Choose AutoAd to {self.operation}"

    @property
    def max_page(self) -> int:
        return max((len(self.ads) - 1) // AUTOADS_PER_PAGE, 0)

    @property
    def current_ads(self) -> list[dict]:
        start = self.page * AUTOADS_PER_PAGE
        return self.ads[start:start + AUTOADS_PER_PAGE]

    def refresh_items(self) -> None:
        self.clear_items()
        self.add_item(AutoAdSelect(self))
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= self.max_page
        if self.max_page > 0:
            self.add_item(self.previous_page)
            self.add_item(self.next_page)

    async def handle_selection(self, interaction: discord.Interaction, value: str) -> None:
        if value == AUTOAD_ALL_VALUE:
            await interaction.response.send_message(
                embed=make_embed("Confirm bulk action", f"You selected **Manage All AutoAds** for `{self.operation}`. Confirm to continue.", color=ERROR_COLOR),
                view=AutoAdConfirmAllView(self),
                ephemeral=True,
            )
            return
        await self.run_single_action(interaction, value)

    async def run_single_action(self, interaction: discord.Interaction, ad_id: str) -> None:
        config = await self.cog.manager.get_config(self.guild_id)
        ad = next((item for item in config.get("ads", []) if item.get("id") == ad_id), None)
        if not ad:
            await interaction.response.send_message(embed=make_embed("Not found", "The selected advertisement no longer exists.", color=ERROR_COLOR), ephemeral=True)
            return
        if self.operation == "edit":
            await interaction.response.send_modal(AutoAdEditModal(self.cog, self.guild_id, ad))
            return
        await interaction.response.defer(ephemeral=True)
        if self.operation == "delete":
            ok = await self.cog.delete_ad(self.guild_id, ad_id)
            await interaction.followup.send(embed=make_embed("Deleted" if ok else "Not found", f"Advertisement `{ad.get('name')}`.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)
        elif self.operation == "send":
            target = self.channel or interaction.channel
            ok = await self.cog.send_specific_ad(target, self.guild_id, ad_id, manual=True) if target else False
            await interaction.followup.send(embed=make_embed("Sent" if ok else "Not sent", f"Advertisement `{ad.get('name')}`.", color=SUCCESS_COLOR if ok else ERROR_COLOR), ephemeral=True)
        elif self.operation == "preview":
            content, embed, files = self.cog.manager.build_payload(ad)
            await interaction.followup.send(content=content, embed=embed or make_embed(ad.get("name", "Advertisement"), ad.get("message") or "No embed content."), files=files, view=AutoAdPreviewView(self.cog, self.guild_id, ad_id), ephemeral=True)

    async def run_bulk_action(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        config = await self.cog.manager.get_config(self.guild_id)
        ads = list(config.get("ads", []))
        if not ads:
            await interaction.followup.send(embed=make_embed("No AutoAds", "There are no advertisements to manage.", color=ERROR_COLOR), ephemeral=True)
            return
        if self.operation == "delete":
            count = len(ads)
            config["ads"] = []
            await self.cog.manager.save_config(self.guild_id, config)
            await interaction.followup.send(embed=make_embed("All AutoAds deleted", f"Deleted `{count}` advertisements.", color=SUCCESS_COLOR), ephemeral=True)
        elif self.operation == "send":
            target = self.channel or interaction.channel
            sent = 0
            if target:
                for ad in ads:
                    if await self.cog.send_specific_ad(target, self.guild_id, ad["id"], manual=True):
                        sent += 1
            await interaction.followup.send(embed=make_embed("Bulk send complete", f"Sent `{sent}` advertisements.", color=SUCCESS_COLOR), ephemeral=True)
        else:
            await interaction.followup.send(embed=make_embed("Select one AutoAd", f"Bulk `{self.operation}` is not supported. Choose a single advertisement.", color=ERROR_COLOR), ephemeral=True)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(self.page - 1, 0)
        self.refresh_items()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.page + 1, self.max_page)
        self.refresh_items()
        await interaction.response.edit_message(view=self)
