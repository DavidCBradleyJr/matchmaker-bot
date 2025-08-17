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


async def slash_guard(interaction: discord.Interaction) -> bool:
    """
    Global guard enforcing Neon-backed timeouts.
    Fail-open on internal errors to avoid bricking the bot.
    """
    try:
        user = interaction.user
        guild_id = interaction.guild_id
        if not user or not guild_id:
            return True  # allow DMs/unknown contexts

        if await is_user_timed_out(user.id, guild_id):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You’re currently timed out from using the bot. Try again later.",
                    ephemeral=True,
                )
            return False

        return True
    except Exception:
        log.exception("slash_guard failed")
        return True


class LFGModeration(commands.Cog):
    """
    LFG moderation helpers + admin timeout commands.

    - Schema is created on cog load.
    - Global slash guard installed ONCE using public API: CommandTree.add_check.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Ensure Neon schema exists before we install the guard and expose commands
        await ensure_schema()

        # Install the global app-command guard exactly once (no private attributes!)
        if not getattr(self.bot, "_slash_guard_installed", False):
            self.bot.tree.add_check(slash_guard)
            setattr(self.bot, "_slash_guard_installed", True)
            log.info("Installed global slash guard (Neon timeouts).")

    async def cog_unload(self) -> None:
        # Optional cleanup for hot-reload workflows
        try:
            self.bot.tree.remove_check(slash_guard)
            setattr(self.bot, "_slash_guard_installed", False)
            log.info("Removed global slash guard.")
        except Exception:
            pass

    # --- Admin helper ---
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

    # --- Commands ---

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
                "This command must be used in a server.",
                ephemeral=True,
            )
            return

        if minutes <= 0:
            await clear_timeout(member.id, guild_id)
            await interaction.response.send_message(
                f"Cleared timeout for {member.mention}.",
                ephemeral=True,
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
                "This command must be used in a server.",
                ephemeral=True,
            )
            return

        timed = await is_user_timed_out(member.id, guild_id)
        if not timed:
            await interaction.response.send_message(
                f"{member.mention} is not timed out.",
                ephemeral=True,
            )
            return

        exp = await get_timeout_expiry(member.id, guild_id)
        pretty = f"<t:{exp}:R>" if exp else "an unknown time"
        await interaction.response.send_message(
            f"{member.mention} is timed out until {pretty}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LFGModeration(bot))
