"""Existing scam exposure report feature."""
from __future__ import annotations

import discord
from discord.ext import commands

from views.scam_report_views import ScamReportView



class ScamReportCog(commands.Cog):
    """Setup command for scam reports."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup_report(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        embed = discord.Embed(
            title="📢 نظام التشهير بالصيادين والنصابين",
            description="إذا تعرضت لعملية نصب، اضغط على الزر أدناه لتقديم بلاغ رسمي وسنقوم بنشره للجميع.",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=ScamReportView(channel))
        await ctx.send(f"✅ تم إعداد نظام البلاغات في {channel.mention}", delete_after=5)


async def setup(bot: commands.Bot) -> None:
    """Load scam report cog."""
    await bot.add_cog(ScamReportCog(bot))
