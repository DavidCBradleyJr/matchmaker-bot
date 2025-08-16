import asyncio
import logging
import discord
from discord.ext import commands
from . import config
from .db import init_pool, get_allowed_guilds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True
# message_content optional; we’re slash-first
# INTENTS.message_content = True

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, application_id=None)

    async def setup_hook(self):
        # DB pool (if configured)
        if config.DATABASE_URL:
            await init_pool(config.DATABASE_URL)

        # Load cogs
        await self.load_extension("bot.cogs.lfg")
        await self.load_extension("bot.cogs.allowlist")  # new

        # Sync application commands
        await self.tree.sync()

bot = Bot()

async def allowed_guilds() -> set[int]:
    if config.ENVIRONMENT == "staging" and config.DATABASE_URL:
        return await get_allowed_guilds("staging")
    return config.STAGING_ALLOWED_GUILDS

@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")
    # Presence
    status_text = config.STAGING_STATUS if config.ENVIRONMENT == "staging" else config.PROD_STATUS
    await bot.change_presence(activity=discord.Game(name=status_text))

    # Staging lock
    if config.ENVIRONMENT == "staging":
        allowed = await allowed_guilds()
        unauthorized = [g for g in bot.guilds if allowed and g.id not in allowed]
        for g in unauthorized:
            logger.warning("Leaving unauthorized guild: %s (%s)", g.name, g.id)
            try:
                await g.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", g.name, g.id)

@bot.event
async def on_guild_join(guild: discord.Guild):
    if config.ENVIRONMENT == "staging":
        allowed = await allowed_guilds()
        if allowed and guild.id not in allowed:
            logger.warning("Invited to unauthorized guild: %s (%s). Leaving.", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", guild.name, guild.id)

async def main():
    await asyncio.gather(
        bot.start(config.DISCORD_TOKEN),
    )

if __name__ == "__main__":
    asyncio.run(main())
