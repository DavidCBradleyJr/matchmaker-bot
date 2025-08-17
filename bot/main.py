# bot/main.py
import os
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

# ---------- Logging ----------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("matchmaker-bot")

# ---------- Global Slash Guard ----------
# This function runs before every app command (via GuardedTree below).
async def slash_guard(interaction: discord.Interaction) -> bool:
    """
    Return False to block; True to allow.

    Here we gate usage on a 'bot timeout' check. If blocked, we send an
    ephemeral message so the user isn't left hanging.
    """
    try:
        from bot.utils.timeouts import is_user_timed_out  # local utility below
    except Exception as e:
        log.exception("Failed to import timeout utility: %s", e)
        # If the guard itself fails, allow rather than bricking all commands.
        return True

    user_id = interaction.user.id if interaction.user else None
    guild_id = interaction.guild_id
    if not user_id or not guild_id:
        # In DMs or missing context—decide your policy. Here we allow.
        return True

    try:
        if await is_user_timed_out(user_id, guild_id):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You’re currently timed out from using the bot. Try again later.",
                    ephemeral=True,
                )
            return False
    except Exception as e:
        log.exception("Timeout check failed: %s", e)
        # Fail-open so commands still work if your DB hiccups
        return True

    return True


class GuardedTree(app_commands.CommandTree):
    """CommandTree that runs `slash_guard` for every incoming slash command."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await slash_guard(interaction)


# ---------- Bot ----------
class MatchmakerBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        # enable what you need; message_content is privileged
        intents.guilds = True
        intents.members = True
        intents.message_content = False  # keep off unless you need it

        super().__init__(
            command_prefix=os.getenv("BOT_PREFIX", "!"),
            intents=intents,
            tree_cls=GuardedTree,  # <— global guard lives here
        )

    async def setup_hook(self) -> None:
        """
        Called inside Client.login() before ready. Load cogs/extensions here.
        """
        # Load your cogs. Add others as you build them.
        # e.g., await self.load_extension("bot.cogs.lfg_ads")
        await self.load_extension("bot.cogs.lfg_moderation")

        # If you want to restrict syncing to specific guilds during dev:
        test_guild_id = os.getenv("TEST_GUILD_ID")
        if test_guild_id:
            guild = discord.Object(id=int(test_guild_id))
            await self.tree.sync(guild=guild)
            log.info("Synced app commands to test guild %s", test_guild_id)
        else:
            await self.tree.sync()
            log.info("Globally synced app commands")


async def run_bot() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")

    bot = MatchmakerBot()
    await bot.start(token)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
