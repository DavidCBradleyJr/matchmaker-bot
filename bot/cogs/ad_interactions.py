# bot/cogs/ad_interactions.py

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import discord
from discord.ext import commands

from ..db import get_pool

log = logging.getLogger("ad_interactions")

CONNECT_PREFIX = "ad_connect:"
REPORT_PREFIX = "ad_report:"

# -------------------- Bootstrap (idempotent) --------------------

BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS lfg_reports (
  id               BIGSERIAL PRIMARY KEY,
  ad_id            BIGINT,
  reporter_id      BIGINT NOT NULL,
  reported_user_id BIGINT,
  guild_id         BIGINT NOT NULL,
  description      TEXT,
  evidence_url     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lfg_reports_guild ON lfg_reports (guild_id, created_at);
"""


async def ensure_bootstrap():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(BOOTSTRAP_SQL)


# -------------------- DB helpers --------------------

async def _get_ad_author(conn: asyncpg.Connection, ad_id: int) -> Optional[int]:
    row = await conn.fetchrow("SELECT author_id FROM lfg_ads WHERE id = $1", ad_id)
    return int(row["author_id"]) if row else None


async def _get_any_post_location(conn: asyncpg.Connection, ad_id: int) -> Optional[tuple[int, int, int]]:
    row = await conn.fetchrow(
        "SELECT guild_id, channel_id, message_id FROM lfg_posts WHERE ad_id = $1 LIMIT 1",
        ad_id,
    )
    if not row:
        return None
    return int(row["guild_id"]), int(row["channel_id"]), int(row["message_id"])


async def _insert_report(
    ad_id: Optional[int],
    reporter_id: int,
    reported_user_id: Optional[int],
    guild_id: int,
    description: str,
    evidence_url: Optional[str],
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO lfg_reports (ad_id, reporter_id, reported_user_id, guild_id, description, evidence_url)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            ad_id, reporter_id, reported_user_id, guild_id, description, evidence_url,
        )


async def _next_report_number(guild_id: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(1) FROM lfg_reports WHERE guild_id = $1", guild_id)
        return int(n or 0)


# -------------------- Mod action Views --------------------

class WarnReasonModal(discord.ui.Modal, title="Warn user"):
    def __init__(self, target_user_id: int, report_id: int, original_link: Optional[str]):
        super().__init__(timeout=180)
        self.target_user_id = target_user_id
        self.report_id = report_id
        self.original_link = original_link
        self.reason = discord.ui.TextInput(
            label="Reason to include in DM",
            placeholder="Short explanation",
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            user = await interaction.client.fetch_user(self.target_user_id)
        except Exception:
            user = interaction.client.get_user(self.target_user_id)

        msg = f"⚠️ You were warned by the moderators.\n• Report ID: #{self.report_id}\n"
        if self.original_link:
            msg += f"• Original report: {self.original_link}\n"
        msg += f"• Reason: {self.reason.value}"

        ok = True
        try:
            if user:
                await user.send(msg)
            else:
                ok = False
        except Exception as e:
            ok = False
            log.warning("Failed to DM warned user %s: %s", self.target_user_id, e)

        await interaction.response.send_message("Warn sent." if ok else "Could not DM the user.", ephemeral=True)


class TimeoutModal(discord.ui.Modal, title="Timeout user"):
    def __init__(self, guild_id: int, target_user_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.target_user_id = target_user_id

        self.hours = discord.ui.TextInput(
            label="Duration (hours)",
            placeholder="e.g. 24",
            required=True,
            max_length=6,
        )
        self.reason = discord.ui.TextInput(
            label="Reason (optional)",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.hours)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            h = int(str(self.hours.value).strip())
            if h <= 0:
                raise ValueError()
        except Exception:
            return await interaction.response.send_message("Invalid number of hours.", ephemeral=True)

        until = datetime.now(timezone.utc) + timedelta(hours=h)
        await put_enforcement(
            interaction.guild.id,  # type: ignore[union-attr]
            self.target_user_id,
            "timeout",
            until,
            str(self.reason.value) if self.reason.value else None,
        )
        await interaction.response.send_message(f"User timed out until <t:{int(until.timestamp())}:F>.", ephemeral=True)


class BanModal(discord.ui.Modal, title="Ban user from bot"):
    def __init__(self, guild_id: int, target_user_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.target_user_id = target_user_id
        self.reason = discord.ui.TextInput(
            label="Reason (optional)",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await put_enforcement(
            interaction.guild.id,  # type: ignore[union-attr]
            self.target_user_id,
            "banned",
            None,
            str(self.reason.value) if self.reason.value else None,
        )
        await interaction.response.send_message("User banned from the bot.", ephemeral=True)


class ReportModView(discord.ui.View):
    def __init__(self, *, report_id: int, reporter_id: int, reported_user_id: Optional[int], original_link: Optional[str]):
        super().__init__(timeout=None)
        self.report_id = report_id
        self.reporter_id = reporter_id
        self.reported_user_id = reported_user_id
        self.original_link = original_link

    @discord.ui.button(label="Ask reporter for more details", style=discord.ButtonStyle.primary, emoji="📩", custom_id="report_action:ask_reporter")
    async def ask_reporter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            reporter = await interaction.client.fetch_user(self.reporter_id)
        except Exception:
            reporter = interaction.client.get_user(self.reporter_id)

        ok = True
        try:
            if reporter:
                await reporter.send(f"Hi! A moderator asked for more details about your report #{self.report_id}. "
                                    f"Please reply with any additional context or evidence.")
            else:
                ok = False
        except Exception as e:
            ok = False
            log.warning("Failed to DM reporter %s for report %s: %s", self.reporter_id, self.report_id, e)

        await interaction.response.send_message(
            "Requested more details from reporter." if ok else "Could not DM the reporter.",
            ephemeral=True,
        )

    @discord.ui.button(label="Warn reported user", style=discord.ButtonStyle.secondary, emoji="⚠️", custom_id="report_action:warn_user")
    async def warn_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.reported_user_id:
            return await interaction.response.send_message("No reported user found on this report.", ephemeral=True)
        await interaction.response.send_modal(WarnReasonModal(self.reported_user_id, self.report_id, self.original_link))

    @discord.ui.button(label="Timeout user", style=discord.ButtonStyle.danger, emoji="⏱️", custom_id="report_action:timeout_user")
    async def timeout_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.reported_user_id:
            return await interaction.response.send_message("No reported user found on this report.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await interaction.response.send_modal(TimeoutModal(interaction.guild.id, self.reported_user_id))

    @discord.ui.button(label="Ban user", style=discord.ButtonStyle.danger, emoji="⛔", custom_id="report_action:ban_user")
    async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.reported_user_id:
            return await interaction.response.send_message("No reported user found on this report.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await interaction.response.send_modal(BanModal(interaction.guild.id, self.reported_user_id))


# -------------------- Report modal (enforces 120 chars) --------------------

class ReportModal(discord.ui.Modal, title="Report Ad"):
    def __init__(self, ad_id: int):
        super().__init__(timeout=180)
        self.ad_id = ad_id

        self.description = discord.ui.TextInput(
            label="Description (max 120 chars)",
            placeholder="Briefly describe the issue",
            required=True,
            max_length=120,  # hard cap in UI
        )
        self.evidence = discord.ui.TextInput(
            label="Evidence link (optional)",
            placeholder="URL to screenshot/video/message",
            required=False,
            max_length=200,
        )
        self.add_item(self.description)
        self.add_item(self.evidence)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Server-side safety: enforce 120 chars even if client misbehaves
        desc = str(self.description.value or "").strip()
        if len(desc) > 120:
            desc = desc[:120]

        evidence_url = str(self.evidence.value).strip() if self.evidence.value else None

        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                reported_user_id = await _get_ad_author(conn, self.ad_id)
                location = await _get_any_post_location(conn, self.ad_id)
        except Exception as e:
            log.exception("Report lookup failed for ad %s: %s", self.ad_id, e)
            reported_user_id = None
            location = None

        # Persist report
        report_id = await _insert_report(
            ad_id=self.ad_id,
            reporter_id=interaction.user.id,
            reported_user_id=reported_user_id,
            guild_id=interaction.guild.id if interaction.guild else 0,  # type: ignore[union-attr]
            description=desc,
            evidence_url=evidence_url,
        )

        # Next report number for channel name (0-based per guild)
        report_num = await _next_report_number(interaction.guild.id) if interaction.guild else report_id  # type: ignore[union-attr]
        safe_name = (interaction.user.name or "reporter").replace(" ", "-").lower()
        channel_name = f"report-{safe_name}-{report_num}"

        if not interaction.guild:
            return await interaction.response.send_message("Report received. Thanks!", ephemeral=True)

        category_id = await get_report_category(interaction.guild.id)
        if not category_id:
            return await interaction.response.send_message(
                "Report received. No review category is configured; ask an admin to run `/lfg_mod set_report_category`.",
                ephemeral=True,
            )

        category = discord.utils.get(interaction.guild.categories, id=category_id)
        if not category:
            return await interaction.response.send_message(
                "Report received, but I can’t find the configured category. Ask an admin to reconfigure it.",
                ephemeral=True,
            )

        # Create the review channel
        try:
            review_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                reason=f"LFG report #{report_id} by {interaction.user} for ad {self.ad_id}",
                topic=f"Report #{report_id} for ad {self.ad_id}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Report received, but I don’t have permission to create review channels (Manage Channels needed).",
                ephemeral=True,
            )

        # Build original message link if present
        original_link = None
        if location:
            g_id, ch_id, m_id = location
            original_link = f"https://discord.com/channels/{g_id}/{ch_id}/{m_id}"

        # Post summary
        embed = discord.Embed(
            title=f"Report #{report_id}",
            description=(
                f"**Ad ID:** {self.ad_id}\n"
                f"**Reporter:** <@{interaction.user.id}>\n"
                f"**Reported user:** {f'<@{reported_user_id}>' if reported_user_id else 'Unknown'}\n"
                f"**Description:** {desc}\n"
                f"{f'**Evidence:** {evidence_url}\\n' if evidence_url else ''}"
                f"{f'**Original:** {original_link}' if original_link else ''}"
            ),
            color=discord.Color.yellow(),
            timestamp=datetime.now(timezone.utc),
        )

        await review_channel.send(
            embed=embed,
            view=ReportModView(
                report_id=report_id,
                reporter_id=interaction.user.id,
                reported_user_id=reported_user_id,
                original_link=original_link,
            ),
        )

        await interaction.response.send_message("Thanks — your report was received.", ephemeral=True)


# -------------------- Ad connect + report button listener --------------------

class AdInteractions(commands.Cog):
    """Handles LFG ad component interactions (Connect & Report) and bootstraps tables."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await ensure_bootstrap()

    @commands.Cog.listener("on_interaction")
    async def handle_component_clicks(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return

        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not custom_id:
            return

        if custom_id.startswith(CONNECT_PREFIX):
            await self._handle_connect(interaction, custom_id)
        elif custom_id.startswith(REPORT_PREFIX):
            await self._handle_report(interaction, custom_id)
        # Mod action buttons are handled by their attached View methods.

    async def _handle_connect(self, interaction: discord.Interaction, custom_id: str):
        try:
            ad_id = int(custom_id.split(":", 1)[1])
        except Exception:
            return await interaction.response.send_message("Invalid ad id.", ephemeral=True)

        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                author_id = await _get_ad_author(conn, ad_id)
                post_loc = await _get_any_post_location(conn, ad_id)
        except Exception as e:
            log.exception("DB error resolving ad %s: %s", ad_id, e)
            return await interaction.response.send_message("Couldn’t resolve this ad. Try again later.", ephemeral=True)

        if not author_id:
            return await interaction.response.send_message("This ad no longer exists.", ephemeral=True)

        try:
            author = await self.bot.fetch_user(author_id)
        except Exception:
            author = self.bot.get_user(author_id)

        clicker = interaction.user

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
                f"If they don’t reply soon, you can ping them in the channel where the ad was posted."
            )
        except Exception as e:
            dm_fail = True
            log.warning("Failed to DM clicker %s for ad %s: %s", clicker.id, ad_id, e)

        await interaction.response.send_message(
            "Check your DMs — I’ve connected you!" if not dm_fail else
            "Tried to connect you via DM, but at least one DM failed (DMs disabled?).",
            ephemeral=True,
        )

    async def _handle_report(self, interaction: discord.Interaction, custom_id: str):
        try:
            ad_id = int(custom_id.split(":", 1)[1])
        except Exception:
            return await interaction.response.send_message("Invalid ad id.", ephemeral=True)

        await interaction.response.send_modal(ReportModal(ad_id))


async def setup(bot: commands.Bot):
    await bot.add_cog(AdInteractions(bot))
