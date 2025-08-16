# bot/cogs/lfg.py
import discord
from discord import app_commands
from discord.ext import commands

class LFG(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Health check.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!", ephemeral=True)

    @app_commands.command(
        name="lfg_basic",
        description="Post a basic LFG message.",
    )
    @app_commands.describe(game="Game name", description="What do you need?")
    async def lfg_basic(
        self,
        interaction: discord.Interaction,
        game: str,
        description: str = "Looking for teammates!",
    ):
        embed = discord.Embed(title=f"LFG | {game}", description=description)
        embed.set_footer(text="Powered by Matchmaker")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LFG(bot))
