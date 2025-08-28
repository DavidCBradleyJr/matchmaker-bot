import logging
import discord
from discord.ext import commands
from .. import db

log = logging.getLogger(__name__)

class GuildEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # increment when joining a new server
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            await db.stats_add_guild(guild.id)
            log.info("Joined guild %s (%d) and recorded in DB.", guild.name, guild.id)
        except Exception:
            log.exception("Failed to record joined guild %d", guild.id)

    # decrement when removed
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            await db.stats_remove_guild(guild.id)
            log.info("Removed from guild %s (%d) and removed from DB.", guild.name, guild.id)
        except Exception:
            log.exception("Failed to remove guild %d from DB", guild.id)

    # on boot: stamp start time + ensure guild list is current
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await db.stats_mark_bot_started()
            for g in self.bot.guilds:
                await db.stats_add_guild(g.id)
            log.info("Startup recorded and backfilled %d guild(s).", len(self.bot.guilds))
        except Exception:
            log.exception("Failed on_ready lifecycle tasks")

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildEvents(bot))
