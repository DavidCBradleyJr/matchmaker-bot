# bot/main.py
import asyncio
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path

# --- always print something first, before heavy imports ---
print("[boot] process starting...", flush=True)

import discord
from discord.ext import commands

# ---------- file-based config loader (deploy-staging / deploy-prod) ----------
DEPLOY_FILES = {
    "staging": "deploy-staging",
    "prod": "deploy-prod",
}

def _detect_env_mode() -> str:
    env = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if env.startswith("stag"):
        return "staging"
    if env.startswith("prod"):
        return "prod"
    fly_app = (os.getenv("FLY_APP_NAME") or "").lower()
    if "staging" in fly_app or "stage" in fly_app:
        return "staging"
    return "prod"

_KV_RE = re.compile(r"""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$""")

def _unquote(val: str) -> str:
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val

def _load_deploy_file(env_mode: str) -> dict:
    fname = DEPLOY_FILES.get(env_mode, "deploy-prod")
    p = Path(fname)
    if not p.exists():
        print(f"[boot] deploy file not found: {p} (skipping)", flush=True)
        return {}
    data: dict[str, str] = {}
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KV_RE.match(line)
            if not m:
                continue
            k, v = m.group(1), _unquote(m.group(2))
            data[k] = v
        print(f"[boot] loaded deploy file: {p} (keys={len(data)})", flush=True)
    except Exception as e:
        print(f"[boot] ERROR reading {p}: {e}", flush=True)
    return data

def _apply_env_defaults(from_file: dict) -> None:
    for k, v in from_file.items():
        if os.getenv(k) is None:
            os.environ[k] = v

_ENV_MODE = _detect_env_mode()
_apply_env_defaults(_load_deploy_file(_ENV_MODE))

# Now that env defaults are in, we can import repo config safely.
try:
    from . import config
except Exception:
    print("[boot] ERROR importing .config. Launch with: python -m bot.main", flush=True)
    raise

# DB helpers: do not let import failure kill startup silently
try:
    from .db import init_pool, get_allowed_guilds
except Exception as e:
    print(f"[boot] WARNING: importing bot.db failed: {e}", flush=True)
    init_pool = None  # type: ignore
    async def get_allowed_guilds(_env: str) -> set[int]:
        return set()

BOOT_TS = time.time()

# ---------- logging ASAP ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bot")
logger.info("[boot] logging configured at level %s", LOG_LEVEL)
logger.info("[boot] environment mode detected: %s", _ENV_MODE)

# ---------- intents ----------
INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = False  # enable only if needed

def _mark(msg: str):
    logger.info("[boot +%.2fs] %s", time.time() - BOOT_TS, msg)

# ---------- health server (for Fly HTTP checks) ----------
async def run_health_server():
    try:
        from aiohttp import web
    except Exception as e:
        logger.critical("aiohttp import failed (required for /health): %s", e)
        raise
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

class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=INTENTS, application_id=None)

    async def setup_hook(self) -> None:
        _mark("setup_hook begin")

        # 1) DB pool (bounded; fail-open)
        if getattr(config, "DATABASE_URL", None) and init_pool:
            try:
                _mark("DB init_pool start")
                await asyncio.wait_for(init_pool(config.DATABASE_URL), timeout=8.0)
                _mark("DB init_pool OK")
            except asyncio.TimeoutError:
                logger.error("DB: init_pool timed out after 8s (continuing)")
            except Exception:
                logger.error("DB: init_pool failed\n%s", traceback.format_exc())

        # 2) Load cogs
        try:
            _mark("cogs load start")
            await self.load_extension("bot.cogs.allowlist")
            await self.load_extension("bot.cogs.status")
            await self.load_extension("bot.cogs.guild_settings")
            await self.load_extension("bot.cogs.lfg_ads")          # defines /lfg group
            await self.load_extension("bot.cogs.lfg_moderation")
            _mark("cogs load OK")
        except Exception:
            logger.error("Cog load failed\n%s", traceback.format_exc())

        # 3) Global slash sync (some commands may be global)
        try:
            _mark("slash sync start")
            synced = await asyncio.wait_for(self.tree.sync(), timeout=15.0)
            _mark(f"slash sync OK (global_count={len(synced)})")
        except asyncio.TimeoutError:
            logger.error("Slash command sync timed out")
        except Exception:
            logger.error("Slash command sync failed\n%s", traceback.format_exc())

        _mark("setup_hook end")

bot = Bot()

async def allowed_guilds() -> set[int]:
    """DB-backed allowlist; never block startup."""
    if (os.getenv("ENVIRONMENT") or "").lower().startswith("stag") or "staging" in (os.getenv("FLY_APP_NAME") or "").lower():
        try:
            return await asyncio.wait_for(get_allowed_guilds("staging"), timeout=5.0)
        except Exception:
            logger.error("Allowed guilds retrieval failed\n%s", traceback.format_exc())
            return set(getattr(config, "STAGING_ALLOWED_GUILDS", []) or [])
    return set()

@bot.event
async def on_ready():
    user = f"{bot.user} ({getattr(bot.user, 'id', '?')})" if bot.user else "unknown"
    _mark(f"CONNECTED to Discord as {user} | Guilds={len(bot.guilds)}")

    # Presence
    env = _ENV_MODE
    status_text = (
        getattr(config, "STAGING_STATUS", "🧪 Staging Bot")
        if env == "staging"
        else getattr(config, "PROD_STATUS", "✅ Matchmaker Bot")
    )
    try:
        await bot.change_presence(activity=discord.Game(name=status_text))
    except Exception:
        logger.exception("Failed to set presence")

    # Staging allowlist enforcement
    if env == "staging":
        allowed = await allowed_guilds()
        logger.info("Staging allowlist (count=%d): %s", len(allowed), sorted(list(allowed)))
        for g in list(bot.guilds):
            if g.id not in allowed:
                logger.warning("Leaving unauthorized guild: %s (%s)", g.name, g.id)
                try:
                    await g.leave()
                except Exception:
                    logger.exception("Failed to leave %s (%s)", g.name, g.id)

    # Per-guild slash sync (register any guild-scoped commands, e.g., /lfg)
    try:
        total = 0
        for g in bot.guilds:
            cmds = await bot.tree.sync(guild=g)
            total += len(cmds)
            _mark(f"guild slash sync OK (guild={g.id}, count={len(cmds)})")
        _mark(f"per-guild slash sync summary: total={total} across {len(bot.guilds)} guild(s)")
    except Exception:
        logger.error("Per-guild slash sync failed\n%s", traceback.format_exc())

@bot.event
async def on_guild_join(guild: discord.Guild):
    env = _ENV_MODE
    if env == "staging":
        allowed = await allowed_guilds()
        if guild.id not in allowed:
            logger.warning("Invited to unauthorized guild: %s (%s). Leaving.", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("Failed to leave %s (%s)", guild.name, guild.id)
            return
    # When the bot joins a new guild, ensure guild-scoped commands are synced there too.
    try:
        cmds = await bot.tree.sync(guild=guild)
        _mark(f"joined guild sync OK (guild={guild.id}, count={len(cmds)})")
    except Exception:
        logger.error("on_guild_join per-guild sync failed\n%s", traceback.format_exc())

# ---------- Entrypoint ----------
async def main():
    _mark("entry begin")

    token = os.getenv("DISCORD_TOKEN") or getattr(config, "DISCORD_TOKEN", None)
    if not token:
        print("[boot] ERROR: DISCORD_TOKEN is not set (check deploy-* file or Fly secret)", flush=True)
        await asyncio.sleep(2)
        raise RuntimeError("DISCORD_TOKEN is not set")

    try:
        await asyncio.gather(
            run_health_server(),   # serve /health for Fly
            bot.start(token),      # connect to Discord
        )
    except Exception:
        logger.critical("bot.start raised\n%s", traceback.format_exc())
        raise

if __name__ == "__main__":
    print("[boot] launching asyncio...", flush=True)
    asyncio.run(main())
