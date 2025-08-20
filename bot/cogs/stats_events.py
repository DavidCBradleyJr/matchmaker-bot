from datetime import datetime, timezone
from discord.ext import commands
import discord
import bot.db as db

class StatsEvents(commands.Cog):
    def __init__(self, bot: commands.Bot | commands.AutoShardedBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await db.stats_set_meta("bot_start_time", datetime.now(timezone.utc).isoformat())
        for g in getattr(self.bot, "guilds", []):
            await db.stats_add_guild(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await db.stats_add_guild(guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await db.stats_remove_guild(guild.id)

async def setup(bot):
    await bot.add_cog(StatsEvents(bot))
