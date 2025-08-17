import asyncio
import logging
import os
import sys
import traceback
import time

import discord
from discord.ext import commands

from . import config
from .db import init_pool, get_allowed_guilds

BOOT_TS = time.time()

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


def _mark(msg: str):
    delta = time.time() - BOOT_TS
    logger.info("[boot +%.2fs] %s", delta, msg)


class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=INTENTS, application_id=None)

    async def setup_hook(self) -> None:
        _mark("setup_hook begin")

        # 1) DB pool — don’t let this block login
        if config.DATABASE_URL:
            try:
                _mark("DB init_pool start")
                await asyncio.wait_for(init_pool(config.DATABASE_URL), timeout=8.0)
                _mark("DB init_pool OK")
            except asyncio.TimeoutError:
                logger.error("DB: init_pool TIMED OUT after 8s — continuing")
            except Exception:
                logger.error("DB: init_pool FAILED\n%s", traceback.format_exc())

        # 2) Load cogs
        try:
            _mark("cogs load start")
            await self.load_extension("bot.cogs.allowlist")
            await self.load_extension("bot.cogs.status")
            await self.load_extension("bot.cogs.guild_settings")
            await self.load_extension("bot.cogs.lfg_ads")
            await self.load_extension("bot.cogs.lfg_moderation")
            await self.load_extension("bot.cogs.ad_interactions")
            _mark("cogs load OK")
        except Exception:
            logger.error("Cog load failed\n%s", traceback.format_exc())

        # 3) Slash command sync
        try:
            _mark("slash sync start")
            synced = await asyncio.wait_for(self.tree.sync(), timeout=15.0)
            _mark(f"slash sync OK (count={len(synced)})")
        except asyncio.TimeoutError:
            logger.error("Slash command sync timed out")
        except Exception:
            logger.error("Slash command sync failed\n%s", traceback.format_exc())

        _mark("setup_hook end")


bot = Bot()


async def allowed_guilds() -> set[int]:
    """Return allowed guilds for staging."""
    if config.ENVIRONMENT != "staging":
        return set()
    try:
        if config.DATABASE_URL:
            return await asyncio.wait_for(get_allowed_guilds("staging"), timeout=5.0)
    except Exception:
        logger.error("Failed to fetch allowed guilds\n%s", traceback.format_exc())
    return set(config.STAGING_ALLOWED_GUILDS or [])


@bot.event
async def on_ready():
    user = f"{bot.user} ({getattr(bot.user, 'id', '?')})" if bot.user else "unknown"
    _mark(f"CONNECTED to Discord as {user} | Guilds={len(bot.guilds)}")

    # Presence
    status_text = config.STAGING_STATUS if config.ENVIRONMENT == "staging" else config.PROD_STATUS
    try:
        await bot.change_presence(activity=discord.Game(name=status_text))
    except Exception:
        logger.exception("Failed to set presence")

    # Staging allowlist enforcement
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
    if config.ENVIRONMENT == "staging":
        allowed = await allowed_guilds()
        if guild.id not in allowed:
            logger.warning("Invited to unauthorized guild: %s (%s). Leaving.", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", guild.name, guild.id)


# ---------- Health server for Fly ----------
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
    _mark(f"health server ON :{port} (/health,/healthz)")


# ---------- Entrypoint ----------
async def main():
    _mark("entry begin")
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    try:
        await asyncio.gather(
            run_health_server(),
            bot.start(config.DISCORD_TOKEN),
        )
    except Exception:
        logger.critical("bot.start raised\n%s", traceback.format_exc())
        raise


if __name__ == "__main__":
    asyncio.run(main())
