"""Discord UI components for scam reports."""
from __future__ import annotations

import datetime as dt

import discord


class ScamReportModal(discord.ui.Modal, title="تقديم بلاغ تشهير بنصاب"):
    """Collect scam report details."""

    scammer_name = discord.ui.TextInput(label="اسم النصاب", placeholder="مثال: @ScammerName", required=True)
    scammer_id = discord.ui.TextInput(label="آيدي النصاب", placeholder="1234567890...", required=True)
    amount = discord.ui.TextInput(label="المبلغ المفقود", placeholder="مثال: 50$", required=True)
    subject = discord.ui.TextInput(label="الموضوع", placeholder="مثال: نصب في حساب", required=True)
    details = discord.ui.TextInput(label="التفاصيل", style=discord.TextStyle.paragraph, placeholder="اشرح ماذا حدث...", required=True)
    evidence_url = discord.ui.TextInput(label="رابط الدليل (صورة)", placeholder="ضع رابط الصورة هنا", required=False)

    def __init__(self, reporter: discord.Member | discord.User, target_channel: discord.TextChannel) -> None:
        super().__init__()
        self.reporter = reporter
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="🚫 تشهير بنصاب 🚫", description="**تم التحقق من هذا التشهير من قبل الإدارة**", color=discord.Color.red())
        embed.add_field(name="👤 المبلغ", value=f"`{self.amount.value}`", inline=True)
        embed.add_field(name="🆔 الآيدي", value=f"`{self.scammer_id.value}`", inline=True)
        embed.add_field(name="📝 الموضوع", value=f"`{self.subject.value}`", inline=False)
        embed.add_field(name="👤 النصاب", value=f"{self.scammer_name.value}", inline=True)
        embed.add_field(name="📢 المبلّغ", value=f"{self.reporter.mention}", inline=True)
        embed.add_field(name="📄 التفاصيل", value=str(self.details.value), inline=False)
        if self.evidence_url.value:
            embed.set_image(url=str(self.evidence_url.value))
        embed.set_footer(text=f"تم النشر في: {self.target_channel.name} | {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await self.target_channel.send(content="@everyone ⚠️ احذروا هذا النصاب!", embed=embed)
        await interaction.response.send_message("✅ تم إرسال بلاغك بنجاح.", ephemeral=True)


class ScamReportView(discord.ui.View):
    """Persistent report button view."""

    def __init__(self, target_channel: discord.TextChannel) -> None:
        super().__init__(timeout=None)
        self.target_channel = target_channel

    @discord.ui.button(label="تقديم بلاغ تشهير 🚨", style=discord.ButtonStyle.danger, custom_id="scam_report_btn", row=0)
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ScamReportModal(interaction.user, self.target_channel))
