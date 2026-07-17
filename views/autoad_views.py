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
