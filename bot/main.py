import os
import sys
import asyncio
import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("matchmaker-bot")

# ---------- Global Slash Guard ----------
async def slash_guard(interaction: discord.Interaction) -> bool:
    """
    Global pre-check for all app commands. Fail-open if the guard has an internal error,
    but always give the user a clear ephemeral message if we intentionally block them.
    """
    try:
        # Import inside the function so a DB/path issue doesn't kill process startup.
        from bot.utils.timeouts import is_user_timed_out
    except Exception:
        log.error("Failed to import timeout utility:\n%s", traceback.format_exc())
        # Fail-open so the bot still works if storage is temporarily unavailable.
        return True

    user = interaction.user
    guild_id = interaction.guild_id
    if not user or not guild_id:
        return True  # Allow DMs / weird contexts

    try:
        if await is_user_timed_out(user.id, guild_id):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You’re currently timed out from using the bot. Try again later.",
                    ephemeral=True,
                )
            return False
    except Exception:
        log.error("Timeout check exploded:\n%s", traceback.format_exc())
        return True  # Fail-open

    return True


class GuardedTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await slash_guard(interaction)


class MatchmakerBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        # Keep message_content off unless you truly need it (privileged intent).
        intents.message_content = False

        super().__init__(
            command_prefix=os.getenv("BOT_PREFIX", "!"),
            intents=intents,
            tree_cls=GuardedTree,  # Global guard for all slash commands
        )

    async def setup_hook(self) -> None:
        # Load cogs here; add others as needed
        try:
            await self.load_extension("bot.cogs.lfg_moderation")
            log.info("Loaded cog: bot.cogs.lfg_moderation")
        except Exception:
            log.error("Failed loading cog bot.cogs.lfg_moderation:\n%s", traceback.format_exc())
            raise

        # DEV: sync to a single test guild if provided for faster propagation
        test_guild_id = os.getenv("TEST_GUILD_ID")
        try:
            if test_guild_id:
                guild = discord.Object(id=int(test_guild_id))
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d app command(s) to test guild %s", len(synced), test_guild_id)
            else:
                synced = await self.tree.sync()
                log.info("Globally synced %d app command(s)", len(synced))
        except Exception:
            log.error("Command sync failed:\n%s", traceback.format_exc())
            # Don't raise; bot can still connect and we can debug sync issues live.

    async def on_ready(self) -> None:
        # Helpful startup breadcrumb in logs
        log.info(
            "Bot connected as %s | ID %s | Guilds: %s",
            self.user, getattr(self.user, "id", "?"), len(self.guilds)
        )

        # Also set a presence to verify visually
        try:
            await self.change_presence(
                activity=discord.Game(name="/ping to test"),
                status=discord.Status.online,
            )
        except Exception:
            log.warning("Failed to set presence:\n%s", traceback.format_exc())


async def run_bot() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")

    bot = MatchmakerBot()

    # Minimal health command so you can confirm slash commands are available
    @bot.tree.command(name="ping", description="Health check")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("Pong!", ephemeral=True)

    log.info("Starting bot...")
    try:
        await bot.start(token)
    except Exception:
        log.critical("bot.start() raised:\n%s", traceback.format_exc())
        raise


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
