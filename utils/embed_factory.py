import discord

SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
WARNING_COLOR = discord.Color.orange()
INFO_COLOR = discord.Color.blurple()


def make_embed(
    title: str = None,
    description: str = None,
    color: discord.Color = INFO_COLOR,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
    )
    return embed