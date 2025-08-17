# bot/cogs/lfg_moderation.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..db import get_pool

log = logging.getLogger(__name__)


async def slash_guard(interaction: discord.Interaction) -> bool:
    """Global guard for slash commands — blocks users who are timed out in DB."""
    if interaction.guild is None or interaction.user is None:
        return True

    pool = await get_pool()
    user_id = interaction.user.id  # type: ignore[attr-defined]
    guild_id = interaction.guild.id

    row = await pool.fetchrow(
        """
        SELECT until_ts
        FROM user_timeouts
        WHERE user_id = $1
          AND guild_id = $2
          AND until_ts > EXTRACT(EPOCH FROM NOW())
        """,
        user_id,
        guild_id,
    )
    if not row:
        return True

    # User is timed out
    until_ts = float(row["until_ts"])
    remaining = max(0, int(until_ts - asyncio.get_event_loop().time()))
    try:
        await interaction.response.send_message(
            f"⏳ You are currently timed out from using LFG commands. "
            f"Try again in **{remaining}** seconds or ask a moderator.",
            ephemeral=True,
        )
    except discord.InteractionResponded:
        pass
    return False


class LFGModeration(commands.Cog):
    """Timeout tools & global gate for slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._prev_interaction_check = None  # type: ignore[var-annotated]

    async def cog_load(self) -> None:
        if not getattr(self.bot, "_slash_guard_installed", False):
            tree = self.bot.tree
            prev = getattr(tree, "interaction_check", None)

            async def _guard_wrapper(interaction: discord.Interaction) -> bool:
                ok = await slash_guard(interaction)
                if not ok:
                    return False
                if prev is not None:
                    return await prev(interaction)  # type: ignore[misc]
                return True

            tree.interaction_check = _guard_wrapper  # type: ignore[assignment]
            setattr(self.bot, "_slash_guard_installed", True)
            self._prev_interaction_check = prev
            log.info("Installed global slash guard (timeouts).")

    async def cog_unload(self) -> None:
        try:
            tree = self.bot.tree
            prev = getattr(self, "_prev_interaction_check", None)
            if prev is not None:
                tree.interaction_check = prev  # type: ignore[assignment]
            else:
                async def _default_ok(_: discord.Interaction) -> bool:
                    return True
                tree.interaction_check = _default_ok  # type: ignore[assignment]
            setattr(self.bot, "_slash_guard_installed", False)
            log.info("Removed global slash guard.")
        except Exception:
            pass

    # --- Slash commands ---

    @app_commands.command(
        name="lfg-timeout",
        description="Timeout (or clear) a user's ability to use the bot.",
    )
    @app_commands.describe(
        member="The member to (un)timeout",
        minutes="Timeout duration in minutes (0 clears).",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def lfg_timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        pool = await get_pool()

        minutes = max(0, minutes)
        if minutes == 0:
            await pool.execute(
                "DELETE FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
                member.id,
                interaction.guild_id,
            )
            await interaction.followup.send(f"✅ Cleared LFG timeout for {member.mention}.", ephemeral=True)
            return

        # Set/replace timeout
        await pool.execute(
            """
            INSERT INTO user_timeouts (user_id, guild_id, until_ts)
            VALUES ($1, $2, EXTRACT(EPOCH FROM NOW()) + $3)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET until_ts = EXCLUDED.until_ts
            """,
            member.id,
            interaction.guild_id,
            minutes * 60,
        )
        await interaction.followup.send(
            f"✅ {member.mention} timed out from LFG for **{minutes}** minutes.",
            ephemeral=True,
        )

    @app_commands.command(
        name="lfg-timeout-status",
        description="Check if a user is timed out from using the bot.",
    )
    @app_commands.describe(member="Member to check (defaults to you)")
    async def lfg_timeout_status(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        pool = await get_pool()
        member = member or interaction.user  # type: ignore[assignment]

        row = await pool.fetchrow(
            """
            SELECT until_ts
            FROM user_timeouts
            WHERE user_id = $1
              AND guild_id = $2
              AND until_ts > EXTRACT(EPOCH FROM NOW())
            """,
            member.id,
            interaction.guild_id,
        )

        if not row:
            await interaction.response.send_message(f"✅ {member.mention} is **not** timed out.", ephemeral=True)
            return

        until_ts = float(row["until_ts"])
        remaining = max(0, int(until_ts - asyncio.get_event_loop().time()))
        await interaction.response.send_message(
            f"⏳ {member.mention} is timed out for **{remaining}** more seconds.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LFGModeration(bot))
