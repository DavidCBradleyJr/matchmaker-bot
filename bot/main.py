import asyncio
import logging
import os
import sys
import time
import traceback

# --- PRINT BEFORE ANY HEAVY IMPORTS (guaranteed visible in logs) ---
print("[boot] process starting...", flush=True)

import discord
from discord.ext import commands

try:
    from . import config
except Exception:
    # If relative import fails because not run as module, this makes it obvious.
    print("[boot] ERROR importing .config. Run with: python -m bot.main", flush=True)
    raise

# Importing pool helpers can fail; don't let that kill startup silently.
try:
    from .db import init_pool, get_allowed_guilds
except Exception as e:
    print(f"[boot] WARNING: importing bot.db failed: {e}", flush=True)
    init_pool = None  # type: ignore
    async def get_allowed_guilds(_env: str) -> set[int]:
        return set()

BOOT_TS = time.time()

# ---------- Logging (set ASAP) ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bot")
logger.info("[boot] logging configured at level %s", LOG_LEVEL)

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

        # 1) DB pool — never block Discord login
        if getattr(config, "DATABASE_URL", None) and init_pool:
            try:
                _mark("DB init_pool start")
                await asyncio.wait_for(init_pool(config.DATABASE_URL), timeout=8.0)
                _mark("DB init_pool OK")
            except asyncio.TimeoutError:
                logger.error("DB: init_pool TIMED OUT after 8s — continuing")
            except Exception:
                logger.error("DB: init_pool FAILED\n%s", traceback.format_exc())

        # 2) Load cogs — keep your develop list
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

        # 3) Slash sync — bounded, non-fatal
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
    """DB-backed allowlist for staging; never block."""
    if getattr(config, "ENVIRONMENT", "") != "staging":
        return set()
    try:
        return await asyncio.wait_for(get_allowed_guilds("staging"), timeout=5.0)
    except Exception:
        logger.error("Allowed guilds retrieval failed\n%s", traceback.format_exc())
        return set(getattr(config, "STAGING_ALLOWED_GUILDS", []) or [])

@bot.event
async def on_ready():
    user = f"{bot.user} ({getattr(bot.user, 'id', '?')})" if bot.user else "unknown"
    _mark(f"CONNECTED to Discord as {user} | Guilds={len(bot.guilds)}")

    # Presence
    status_text = (
        getattr(config, "STAGING_STATUS", "Matchmaker (staging)")
        if getattr(config, "ENVIRONMENT", "") == "staging"
        else getattr(config, "PROD_STATUS", "Matchmaker")
    )
    try:
        await bot.change_presence(activity=discord.Game(name=status_text))
    except Exception:
        logger.exception("Failed to set presence")

    # Staging allowlist enforcement
    if getattr(config, "ENVIRONMENT", "") == "staging":
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
    if getattr(config, "ENVIRONMENT", "") == "staging":
        allowed = await allowed_guilds()
        if guild.id not in allowed:
            logger.warning("Invited to unauthorized guild: %s (%s). Leaving.", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", guild.name, guild.id)

async def maybe_health_server():
    """Start /healthz only if explicitly enabled. No dependency if disabled."""
    if os.getenv("AIOHTTP", "0") != "1":
        _mark("health server disabled (AIOHTTP env var != 1)")
        return
    try:
        from aiohttp import web
    except Exception as e:
        logger.error("Health server requested but aiohttp import failed: %s", e)
        return

    async def health(_req):
        return web.Response(text="ok", status=200)

    app = web.Application()
    app.add_routes([web.get("/health"), web.get("/healthz")])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    _mark(f"health server ON :{port} (/health,/healthz)")

# ---------- Entrypoint ----------
async def main():
    _mark("entry begin")
    token = getattr(config, "DISCORD_TOKEN", None)
    if not token:
        print("[boot] ERROR: DISCORD_TOKEN is not set", flush=True)
        raise RuntimeError("DISCORD_TOKEN is not set")

    try:
        await asyncio.gather(
            maybe_health_server(),
            bot.start(token),
        )
    except Exception:
        logger.critical("bot.start raised\n%s", traceback.format_exc())
        raise

if __name__ == "__main__":
    print("[boot] launching asyncio...", flush=True)
    asyncio.run(main())
