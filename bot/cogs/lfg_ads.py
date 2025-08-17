# bot/cogs/ad_interactions.py

from __future__ import annotations

import logging
from typing import Optional

import asyncpg
import discord
from discord.ext import commands

from ..db import get_pool

log = logging.getLogger("ad_interactions")

CONNECT_PREFIX = "ad_connect:"
REPORT_PREFIX = "ad_report:"


# ---------- DB helpers ----------

async def _get_ad_author(conn: asyncpg.Connection, ad_id: int) -> Optional[int]:
    row = await conn.fetchrow("SELECT author_id FROM lfg_ads WHERE id = $1", ad_id)
    return int(row["author_id"]) if row else None


async def _get_any_post_location(conn: asyncpg.Connection, ad_id: int) -> Optional[tuple[int, int, int]]:
    """
    Return (guild_id, channel_id, message_id) for one post of this ad, if exists.
    """
    row = await conn.fetchrow(
        "SELECT guild_id, channel_id, message_id FROM lfg_posts WHERE ad_id = $1 LIMIT 1",
        ad_id,
    )
    if not row:
        return None
    return int(row["guild_id"]), int(row["channel_id"]), int(row["message_id"])


# ---------- Modal for reports ----------

class ReportModal(discord.ui.Modal, title="Report Ad"):
    def __init__(self, ad_id: int):
        super().__init__(timeout=180)
        self.ad_id = ad_id
        # discord.py 2.4 TextInput
        self.reason = discord.ui.TextInput(
            label="What’s the issue?",
            placeholder="Spam, scam, harassment, wrong channel, etc.",
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        pool = get_pool()
        # Log the report with as much context as we can gather
        try:
            async with pool.acquire() as conn:
                author_id = await _get_ad_author(conn, self.ad_id)
                location = await _get_any_post_location(conn, self.ad_id)
        except Exception as e:
            log.exception("Report lookup failed for ad %s: %s", self.ad_id, e)
            author_id = None
            location = None

        log.info(
            "REPORT ad_id=%s by user_id=%s reason=%r ad_author=%s location=%s",
            self.ad_id,
            interaction.user.id,
            str(self.reason.value),
            author_id,
            location,
        )

        # Optional: DM to moderators or post to a mod channel.
        # If you have a configured mod channel per guild, you can look it up here and forward the report.

        await interaction.response.send_message(
            "Thanks — your report was received. Our moderators will review it.",
            ephemeral=True,
        )


# ---------- Cog that handles all component interactions ----------

class AdInteractions(commands.Cog):
    """Handles button interactions for LFG ads (connect & report)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_interaction")
    async def handle_component_clicks(self, interaction: discord.Interaction):
        # We only care about component interactions (buttons).
        if interaction.type is not discord.InteractionType.component:
            return

        custom_id = (interaction.data or {}).get("custom_id")  # type: ignore[assignment]
        if not custom_id:
            return

        if custom_id.startswith(CONNECT_PREFIX):
            await self._handle_connect(interaction, custom_id)
        elif custom_id.startswith(REPORT_PREFIX):
            await self._handle_report(interaction, custom_id)

    async def _handle_connect(self, interaction: discord.Interaction, custom_id: str):
        # Parse ad_id
        try:
            ad_id = int(custom_id.split(":", 1)[1])
        except Exception:
            return await interaction.response.send_message("Invalid ad id.", ephemeral=True)

        pool = get_pool()

        # Lookup ad author
        try:
            async with pool.acquire() as conn:
                author_id = await _get_ad_author(conn, ad_id)
                post_loc = await _get_any_post_location(conn, ad_id)
        except Exception as e:
            log.exception("DB error resolving ad %s: %s", ad_id, e)
            return await interaction.response.send_message("Couldn’t resolve this ad. Try again later.", ephemeral=True)

        if not author_id:
            return await interaction.response.send_message("This ad no longer exists.", ephemeral=True)

        # Resolve user objects
        try:
            author = await self.bot.fetch_user(author_id)
        except Exception:
            author = self.bot.get_user(author_id)

        clicker = interaction.user

        log.info(
            "CONNECT clicker_id=%s ad_id=%s author_id=%s location=%s",
            getattr(clicker, "id", None),
            ad_id,
            author_id,
            post_loc,
        )

        # DM both sides (best-effort; users can block DMs)
        dm_fail = False
        try:
            if author:
                await author.send(
                    f"🤝 Someone is interested in your LFG ad #{ad_id}! User: **{clicker}** (ID: {clicker.id}). "
                    f"You can reply here to connect."
                )
        except Exception as e:
            dm_fail = True
            log.warning("Failed to DM ad author %s for ad %s: %s", author_id, ad_id, e)

        try:
            await clicker.send(
                f"🤝 You’ve been connected with the ad owner for LFG ad #{ad_id}. "
                f"If they don’t message back soon, you can ping them in the channel where the ad was posted."
            )
        except Exception as e:
            dm_fail = True
            log.warning("Failed to DM clicker %s for ad %s: %s", clicker.id, ad_id, e)

        # Acknowledge ephemerally in the channel
        if dm_fail:
            await interaction.response.send_message(
                "Tried to connect you via DM, but at least one DM failed. They may have DMs disabled.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("Check your DMs — I’ve connected you!", ephemeral=True)

    async def _handle_report(self, interaction: discord.Interaction, custom_id: str):
        try:
            ad_id = int(custom_id.split(":", 1)[1])
        except Exception:
            return await interaction.response.send_message("Invalid ad id.", ephemeral=True)

        log.info("REPORT_CLICK user_id=%s ad_id=%s", interaction.user.id, ad_id)
        # Show a modal to collect details
        await interaction.response.send_modal(ReportModal(ad_id))


async def setup(bot: commands.Bot):
    await bot.add_cog(AdInteractions(bot))
