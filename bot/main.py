import asyncio
import logging

import discord
from discord.ext import commands

from bot import config
from bot.db import init_pool, get_allowed_guilds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = False

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, application_id=None)

    async def setup_hook(self):
        # Connect DB (if configured) and create tables
        if config.DATABASE_URL:
            await init_pool(config.DATABASE_URL)

        # Load cogs
        # await self.load_extension("bot.cogs.lfg")
        await self.load_extension("bot.cogs.allowlist")
        await self.load_extension("bot.cogs.status")
        await self.load_extension("bot.cogs.guild_settings")
        await self.load_extension("bot.cogs.lfg_ads")

        # Register slash commands globally
        await self.tree.sync()

bot = Bot()

async def allowed_guilds() -> set[int]:
    """Return the set of guild IDs allowed for STAGING. Empty set = allow no one."""
    if config.ENVIRONMENT != "staging":
        return set()
    if config.DATABASE_URL:
        return await get_allowed_guilds("staging")
    return set(config.STAGING_ALLOWED_GUILDS or [])

@bot.event
async def on_ready():
    user = f"{bot.user} ({getattr(bot.user, 'id', '?')})" if bot.user else "unknown"
    logger.info("Logged in as %s", user)

    # Presence
    status_text = config.STAGING_STATUS if config.ENVIRONMENT == "staging" else config.PROD_STATUS
    try:
        await bot.change_presence(activity=discord.Game(name=status_text))
    except Exception:
        logger.exception("Failed to set presence")

    # STAGING: deny-by-default — leave any non-allowed guilds
    if config.ENVIRONMENT == "staging":
        allowed = await allowed_guilds()
        logger.info("Staging allowlist (count=%d): %s", len(allowed), sorted(list(allowed)))
        for g in list(bot.guilds):
            if g.id not in allowed:
                logger.warning("Leaving unauthorized guild: %s (%s)", g.name, g.id)
                try:
                    await g.leave()
                except Exception:
                    logger.exception("Failed to leave %s (%s)", g.name, g.id)

@bot.event
async def on_guild_join(guild: discord.Guild):
    # STAGING: deny-by-default on any new join
    if config.ENVIRONMENT == "staging":
        allowed = await allowed_guilds()
        if guild.id not in allowed:
            logger.warning("Invited to unauthorized guild: %s (%s). Leaving.", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", guild.name, guild.id)

async def run_health_server():
    from aiohttp import web

    async def health(_req):
        return web.Response(text="ok", status=200)

    app = web.Application()
    app.add_routes([web.get("/health", health)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()


async def main():
    await asyncio.gather(
        run_health_server(),
        bot.start(config.DISCORD_TOKEN),
    )

if __name__ == "__main__":
    asyncio.run(main())
