# bot/main.py
import asyncio
import logging
import os
import sys
import traceback

import discord
from discord.ext import commands

from . import config
from .db import init_pool, get_allowed_guilds

# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bot")

# ---------- Intents ----------
INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = False  # keep off unless you actually need it

class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=INTENTS, application_id=None)

    async def setup_hook(self) -> None:
        # 1) DB pool (don’t let it brick Discord login if Neon is slow/misconfigured)
        if config.DATABASE_URL:
            try:
                logger.info("DB: init_pool start")
                await asyncio.wait_for(init_pool(config.DATABASE_URL), timeout=10.0)
                logger.info("DB: init_pool OK")
            except asyncio.TimeoutError:
                logger.error("DB: init_pool timed out after 10s — continuing without DB")
            except Exception:
                logger.error("DB: init_pool failed\n%s", traceback.format_exc())

        # 2) Load cogs (keep your existing list)
        try:
            # await self.load_extension("bot.cogs.lfg")
            await self.load_extension("bot.cogs.allowlist")
            await self.load_extension("bot.cogs.status")
            await self.load_extension("bot.cogs.guild_settings")
            await self.load_extension("bot.cogs.lfg_ads")
            await self.load_extension("bot.cogs.lfg_moderation")
            await self.load_extension("bot.cogs.ad_interactions")
            logger.info("Cogs loaded")
        except Exception:
            logger.error("Failed loading cogs\n%s", traceback.format_exc())

        try:
            synced = await asyncio.wait_for(self.tree.sync(), timeout=20.0)
            logger.info("Slash command sync complete (count=%d)", len(synced))
        except asyncio.TimeoutError:
            logger.error("Slash command sync timed out — continuing")
        except Exception:
            logger.error("Slash command sync failed\n%s", traceback.format_exc())

bot = Bot()

async def allowed_guilds() -> set[int]:
    """Return the set of guild IDs allowed for STAGING. Empty set = allow no one."""
    if config.ENVIRONMENT != "staging":
        return set()
    # Prefer DB-backed allowlist if pool is up; otherwise fall back to static list
    try:
        if config.DATABASE_URL:
            return await get_allowed_guilds("staging")
    except Exception:
        logger.error("Failed to fetch allowed guilds from DB\n%s", traceback.format_exc())
    return set(config.STAGING_ALLOWED_GUILDS or [])

@bot.event
async def on_ready():
    user = f"{bot.user} ({getattr(bot.user, 'id', '?')})" if bot.user else "unknown"
    logger.info("Logged in as %s | Guilds=%d", user, len(bot.guilds))

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

# ---------- Fly health server (keeps platform happy) ----------
async def run_health_server():
    from aiohttp import web

    async def health(_req):
        return web.Response(text="ok", status=200)

    app = web.Application()
    app.add_routes([web.get("/health", health), web.get("/healthz", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Health server started on :%d (/health,/healthz)", port)

# ---------- Entrypoint ----------
async def main():
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    await asyncio.gather(
        run_health_server(),
        bot.start(config.DISCORD_TOKEN),
    )

if __name__ == "__main__":
    asyncio.run(main())
