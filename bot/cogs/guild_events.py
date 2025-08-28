import logging
import discord
from discord.ext import commands
from .. import db

log = logging.getLogger(__name__)

class GuildEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Record newly joined guild in DB."""
        try:
            await db.stats_add_guild(guild.id)
            log.info("Joined guild %s (%d) and recorded in DB.", guild.name, guild.id)
        except Exception:
            log.exception("Failed to record joined guild %d", guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Remove guild from DB when the bot leaves/is removed."""
        try:
            await db.stats_remove_guild(guild.id)
            log.info("Removed from guild %s (%d) and removed from DB.", guild.name, guild.id)
        except Exception:
            log.exception("Failed to remove guild %d from DB", guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Optional safety: backfill all current guilds at boot.
        Ensures DB count matches reality after restarts/deploys.
        """
        try:
            for g in self.bot.guilds:
                await db.stats_add_guild(g.id)
            log.info("Backfilled %d guild(s) into DB on_ready.", len(self.bot.guilds))
        except Exception:
            log.exception("Failed backfilling guilds on_ready")

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildEvents(bot))
