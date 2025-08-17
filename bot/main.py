# bot/main.py
import os
import sys
import asyncio
import logging
import time
import traceback

import discord
from discord import app_commands
from discord.ext import commands


try:
    from bot.db import init_pool
except Exception:  # pragma: no cover
    init_pool = None  # type: ignore

START_TS = time.time()

def log_setup():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)

log_setup()
log = logging.getLogger("matchmaker-bot")


# ---------- Global Slash Guard ----------
async def slash_guard(interaction: discord.Interaction) -> bool:
    try:
        from bot.utils.timeouts import is_user_timed_out  # Neon-backed
        user = interaction.user
        gid = interaction.guild_id
        if not user or not gid:
            return True
        if await is_user_timed_out(user.id, gid):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You’re currently timed out from using the bot. Try again later.",
                    ephemeral=True,
                )
            return False
    except Exception:
        log.error("slash_guard failed:\n%s", traceback.format_exc())
        return True  # fail-open
    return True


class GuardedTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await slash_guard(interaction)


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        # Keep message content off unless you need it:
        intents.message_content = False

        super().__init__(
            command_prefix=os.getenv("BOT_PREFIX", "!"),
            intents=intents,
            tree_cls=GuardedTree,
        )

        self._startup_marks = []

    def _mark(self, msg: str):
        now = time.time() - START_TS
        self._startup_marks.append(f"+{now:05.2f}s {msg}")
        log.info(msg)

    async def setup_hook(self) -> None:
        self._mark("setup_hook: begin")

        # 1) Init Neon pool (bounded). If it takes too long, warn and continue.
        if init_pool:
            try:
                self._mark("DB: init_pool start")
                await asyncio.wait_for(init_pool(os.getenv("DATABASE_URL")), timeout=8.0)
                self._mark("DB: init_pool OK")
            except asyncio.TimeoutError:
                log.error("DB: init_pool timed out after 8s (continuing; bot will still connect)")
            except Exception:
                log.error("DB: init_pool failed:\n%s", traceback.format_exc())

        # 2) Ensure timeout schema (bounded). Don’t let it block Discord connect.
        try:
            self._mark("Timeouts: ensure_schema start")
            from bot.utils.timeouts import ensure_schema
            await asyncio.wait_for(ensure_schema(), timeout=5.0)
            self._mark("Timeouts: ensure_schema OK")
        except asyncio.TimeoutError:
            log.error("Timeouts: ensure_schema timed out after 5s (continuing)")
        except Exception:
            log.error("Timeouts: ensure_schema failed:\n%s", traceback.format_exc())

        # 3) Load cogs (bounded per-cog)
        try:
            self._mark("Cog load: bot.cogs.lfg_moderation start")
            await asyncio.wait_for(self.load_extension("bot.cogs.lfg_moderation"), timeout=5.0)
            self._mark("Cog load: bot.cogs.lfg_moderation OK")
        except asyncio.TimeoutError:
            log.error("Cog load: lfg_moderation timed out (continuing)")
        except Exception:
            log.error("Cog load: lfg_moderation failed:\n%s", traceback.format_exc())

        # 4) Register a quick health command
        @self.tree.command(name="ping", description="Health check")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("Pong!", ephemeral=True)

        # 5) Sync in setup_hook (safe); bounded but non-fatal
        try:
            test_guild_id = os.getenv("TEST_GUILD_ID")
            if test_guild_id:
                guild = discord.Object(id=int(test_guild_id))
                synced = await asyncio.wait_for(self.tree.sync(guild=guild), timeout=10.0)
                self._mark(f"Command sync: {len(synced)} to guild {test_guild_id}")
            else:
                synced = await asyncio.wait_for(self.tree.sync(), timeout=15.0)
                self._mark(f"Command sync: global {len(synced)}")
        except asyncio.TimeoutError:
            log.error("Command sync timed out (continuing)")
        except Exception:
            log.error("Command sync failed:\n%s", traceback.format_exc())

        self._mark("setup_hook: end")

    async def on_ready(self) -> None:
        self._mark(f"Connected to Discord as {self.user} | Guilds={len(self.guilds)}")
        try:
            await self.change_presence(activity=discord.Game(name="/ping"), status=discord.Status.online)
        except Exception:
            log.warning("Presence update failed:\n%s", traceback.format_exc())

        # Dump startup timeline for post-mortem clarity
        log.info("Startup timeline:\n%s", "\n".join(self._startup_marks))


async def _run() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")

    bot = Bot()
    # Start the gateway; any pre-connect stalls will be visible from setup_hook marks
    try:
        log.info("Starting Discord bot ...")
        await bot.start(token)
    except Exception:
        log.critical("bot.start() raised:\n%s", traceback.format_exc())
        raise


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
