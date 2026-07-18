"""Discord UI components for sales relay and moderation."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from cogs.sales_moderation import SalesModerationCog


class PunishmentView(discord.ui.View):
    """Moderator punishment buttons for users reaching warning limits."""

    def __init__(self, user: discord.Member | discord.User) -> None:
        super().__init__(timeout=180)
        self.user = user

    async def _member_or_error(self, interaction: discord.Interaction) -> discord.Member | None:
        if isinstance(self.user, discord.Member):
            return self.user
        if interaction.guild:
            member = interaction.guild.get_member(self.user.id)
            if member:
                return member
        await interaction.followup.send("❌ لا يمكن تنفيذ العقوبة لأن المستخدم ليس عضوًا في السيرفر حاليًا.", ephemeral=True)
        return None

    @discord.ui.button(label="Time Out", style=discord.ButtonStyle.secondary)
    async def timeout(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        member = await self._member_or_error(interaction)
        if not member:
            return
        await member.timeout(dt.timedelta(minutes=60), reason="Auto-Punishment")
        await interaction.followup.send(f"✅ تم عمل Timeout لـ {member.mention}", ephemeral=True)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        member = await self._member_or_error(interaction)
        if not member:
            return
        await member.kick(reason="Auto-Punishment")
        await interaction.followup.send(f"✅ تم طرد {member.mention}", ephemeral=True)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        member = await self._member_or_error(interaction)
        if not member:
            return
        await member.ban(reason="Auto-Punishment")
        await interaction.followup.send(f"✅ تم حظر {member.mention}", ephemeral=True)


class WarnReasonModal(discord.ui.Modal, title="إرسال تحذير للمنشور"):
    """Collect a warning reason from a moderator."""

    reason = discord.ui.TextInput(
        label="سبب التحذير",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب السبب هنا...",
        required=True,
    )

    def __init__(
        self,
        cog: "SalesModerationCog",
        target_user: discord.Member | discord.User,
        original_msg: discord.Message,
        target_channel: discord.TextChannel | None,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.target_user = target_user
        self.original_msg = original_msg
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_warning_submit(interaction, self.target_user, self.original_msg, self.target_channel, str(self.reason.value))


class SellerDetailsView(discord.ui.View):
    """Seller detail buttons shown privately to users."""

    def __init__(self, cog: "SalesModerationCog", seller_name: str, seller_id: int, channel_id: int, original_msg: discord.Message) -> None:
        super().__init__(timeout=180)
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
        permissions = getattr(interaction.user, "guild_permissions", None)
        if not permissions or not permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر للمشرفين فقط!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        await interaction.response.send_modal(
            WarnReasonModal(
                self.cog,
                self.original_msg.author,
                self.original_msg,
                channel if isinstance(channel, discord.TextChannel) else None,
            )
        )


class MainSalesView(discord.ui.View):
    """Public contact button for relayed sales posts."""

    def __init__(self, cog: "SalesModerationCog", seller_name: str, seller_id: int, channel_id: int, original_msg: discord.Message) -> None:
        super().__init__(timeout=180)
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
        await interaction.response.send_message(
            embed=embed,
            view=SellerDetailsView(self.cog, self.seller_name, self.seller_id, self.channel_id, self.original_msg),
            ephemeral=True,
        )
