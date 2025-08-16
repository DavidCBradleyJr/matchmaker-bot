import discord
from discord import app_commands
from discord.ext import commands
from ..db import get_pool

class GuildSettings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="lfg_channel", description="Configure the LFG ads channel")

    @group.command(name="set", description="Set the channel where LFG ads should be broadcast")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        async with get_pool().acquire() as conn:
            await conn.execute("""
                INSERT INTO guild_settings (guild_id, lfg_channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET lfg_channel_id = EXCLUDED.lfg_channel_id, updated_at=NOW()
            """, interaction.guild.id, channel.id)

        await interaction.response.send_message(
            f"✅ LFG ads will be posted in {channel.mention}.",
            ephemeral=True
        )

    @group.command(name="show", description="Show the current LFG ads channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def show_channel(self, interaction: discord.Interaction):
        async with get_pool().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT lfg_channel_id FROM guild_settings WHERE guild_id=$1",
                interaction.guild.id
            )
        if row and row["lfg_channel_id"]:
            ch = interaction.guild.get_channel(int(row["lfg_channel_id"]))
            msg = f"📣 Current LFG channel: {ch.mention if ch else f'<#{row['lfg_channel_id']}>'}"
        else:
            msg = "ℹ️ No LFG channel set yet. Use `/lfg_channel set #channel`."
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildSettings(bot))
