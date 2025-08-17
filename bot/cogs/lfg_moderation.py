# bot/cogs/lfg_moderation.py
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.timeouts import (
    ensure_schema,
    is_user_timed_out,
    get_timeout_expiry,
    set_timeout,
    clear_timeout,
)

log = logging.getLogger(__name__)

# -------------------------------------------------------
# Global guard used by ALL app commands (via setup())
# -------------------------------------------------------
async def slash_guard(interaction: discord.Interaction) -> bool:
    try:
        user = interaction.user
        guild_id = interaction.guild_id
        if not user or not guild_id:
            return True

        # Block if the user is timed out in this guild
        if await is_user_timed_out(user.id, guild_id):
            # Tell the user why it was blocked (ephemeral)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You’re currently timed out from using the bot. Try again later.",
                    ephemeral=True,
                )
            return False

        return True
    except Exception:
        log.exception("slash_guard failed")
        # fail-open so we don't brick commands if guard crashes
        return True


class LFGModeration(commands.Cog):
    """Minimal moderation cog (timeouts) + global diagnostics for slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Keep your schema bootstrap
        await ensure_schema()

    # ------------------------------
    # Global diagnostics (minimal)
    # ------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            # This confirms whether the bot SEES the interaction at all
            cmd = getattr(interaction, "command", None)
            qn = getattr(cmd, "qualified_name", None)
            log.info(
                "interaction: type=%s user=%s guild=%s channel=%s cmd=%s responded=%s",
                getattr(interaction.type, "name", interaction.type),
                getattr(interaction.user, "id", None),
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                qn,
                interaction.response.is_done(),
            )
        except Exception:
            log.exception("on_interaction logger failed")

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        try:
            log.info(
                "app_command_completed: %s by user=%s guild=%s",
                command.qualified_name,
                getattr(interaction.user, "id", None),
                interaction.guild_id,
            )
        except Exception:
            log.exception("on_app_command_completion logger failed")

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        # One place to see *why* a slash command failed (any cog)
        log.exception(
            "app_command_error for cmd=%s user=%s guild=%s",
            getattr(getattr(interaction, "command", None), "qualified_name", "?"),
            getattr(interaction.user, "id", None),
            interaction.guild_id,
            exc_info=error,
        )
        # Make sure the user gets feedback
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ That command failed. The error has been logged.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⚠️ That command failed. The error has been logged.",
                    ephemeral=True,
                )
        except Exception:
            # Don't raise from error handler
            log.exception("failed to send error followup")

    # ------------------------------
    # Admin timeout helpers (unchanged)
    # ------------------------------
    async def is_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user or not interaction.guild:
            return False
        perms = interaction.user.guild_permissions  # type: ignore[attr-defined]
        ok = perms.manage_guild or perms.administrator
        if not ok and not interaction.response.is_done():
            await interaction.response.send_message(
                "You need **Manage Server** or **Administrator** to use this.",
                ephemeral=True,
            )
        return ok

    @app_commands.command(
        name="lfg-timeout",
        description="Timeout (or clear) a user's ability to use the bot."
    )
    @app_commands.describe(
        member="The member to (un)timeout",
        minutes="Timeout duration in minutes (0 clears).",
    )
    async def lfg_timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
    ):
        if not await self.is_admin(interaction):
            return
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return
        if minutes <= 0:
            await clear_timeout(member.id, guild_id)
            await interaction.response.send_message(
                f"Cleared timeout for {member.mention}.", ephemeral=True
            )
            return
        await set_timeout(member.id, guild_id, minutes)
        await interaction.response.send_message(
            f"Timed out {member.mention} for {minutes} minute(s).",
            ephemeral=True,
        )

    @app_commands.command(
        name="lfg-timeout-status",
        description="Check if a user is timed out from using the bot."
    )
    @app_commands.describe(member="Member to check (defaults to you)")
    async def lfg_timeout_status(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        member = member or interaction.user  # type: ignore[assignment]
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return
        timed = await is_user_timed_out(member.id, guild_id)
        if not timed:
            await interaction.response.send_message(
                f"{member.mention} is not timed out.", ephemeral=True
            )
            return
        exp = await get_timeout_expiry(member.id, guild_id)
        pretty = f"<t:{exp}:R>" if exp else "an unknown time"
        await interaction.response.send_message(
            f"{member.mention} is timed out until {pretty}.", ephemeral=True
        )


# -------------------------------------------------------
# Extension setup: register GLOBAL interaction check
# -------------------------------------------------------
async def setup(bot: commands.Bot) -> None:
    # Global interaction check for ALL app commands
    @bot.tree.interaction_check
    async def _global_interaction_check(interaction: discord.Interaction) -> bool:
        return await slash_guard(interaction)

    await bot.add_cog(LFGModeration(bot))
