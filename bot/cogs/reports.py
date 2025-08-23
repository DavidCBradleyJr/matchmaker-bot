from __future__ import annotations

import os
import re
import logging
from datetime import datetime, timezone, timedelta
import discord
from discord import ui
from discord.ext import commands

from ..database import reports_db, moderation_db

LOGGER = logging.getLogger("reports")
if not LOGGER.handlers:
    import sys
    h = logging.StreamHandler(stream=sys.stdout)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s reports: %(message)s")
    h.setFormatter(fmt)
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

MAIN_BOT_GUILD_ID = int(os.getenv("MAIN_BOT_GUILD_ID", "0"))
REPORTS_CATEGORY_ID = int(os.getenv("REPORTS_CATEGORY_ID", "0"))
OWNER_USER_ID = int(os.getenv("OWNER_ID", "0"))
MAX_DESC = 120

REPORT_ID_RE = re.compile(r"Ad\s*Report\s*#\s*(\d+)", re.IGNORECASE)
BACKTICK_NUM_RE = re.compile(r"\(`?(\d+)`?\)")

def _slug_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")[:24] or "user"

def _is_mod(member: discord.Member) -> bool:
    if OWNER_USER_ID and member.id == OWNER_USER_ID:
        return True
    p = member.guild_permissions
    return bool(p.manage_guild or p.manage_channels or p.administrator)

def _parse_ctx_from_message(msg: discord.Message | None) -> dict[str, int | None]:
    report_id = reported_id = ad_id = origin_guild_id = None
    if not msg:
        return {"report_id": None, "reported_id": None, "ad_id": None, "origin_guild_id": None}
    try:
        if isinstance(msg.channel, discord.TextChannel):
            m = re.search(r"report-(\d+)-", msg.channel.name)
            if m:
                report_id = int(m.group(1))
            if msg.channel.topic:
                mg = re.search(r"From guild\s+(\d+)", msg.channel.topic, re.IGNORECASE)
                if mg:
                    origin_guild_id = int(mg.group(1))
        for emb in msg.embeds or ():
            if emb.title:
                m = REPORT_ID_RE.search(emb.title)
                if m:
                    report_id = report_id or int(m.group(1))
            for f in emb.fields:
                if f.name and f.name.lower() == "ad":
                    m = re.search(r"`(\d+)`", str(f.value))
                    if m:
                        ad_id = int(m.group(1))
                if f.name and f.name.lower() == "reported":
                    m = BACKTICK_NUM_RE.search(str(f.value))
                    if m:
                        reported_id = int(m.group(1))
        return {"report_id": report_id, "reported_id": reported_id, "ad_id": ad_id, "origin_guild_id": origin_guild_id}
    except Exception:
        return {"report_id": report_id, "reported_id": reported_id, "ad_id": ad_id, "origin_guild_id": origin_guild_id}

# ---------------------- Modals ----------------------

class AskReporterModal(ui.Modal, title="Ask Reporter for More Info"):
    def __init__(self, report_id: int, reporter: discord.User, channel_id: int):
        super().__init__(timeout=180)
        self.report_id = report_id
        self.reporter = reporter
        self.channel_id = channel_id
        self.message = ui.TextInput(label="Message to reporter", max_length=300, required=True)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.reporter.send(
                f"👋 A moderator has asked for more info about your report:\n> {self.message.value}\n\n"
                "Reply here and I’ll forward your messages back to the moderators."
            )
            # Open conversation bridge
            await reports_db.open_conversation(self.report_id, self.reporter.id, self.channel_id)
            await interaction.response.send_message("✅ DM sent to reporter. Their replies will show up here.", ephemeral=True)
        except Exception:
            LOGGER.exception("DM to reporter failed")
            await interaction.response.send_message("Couldn’t DM the reporter (DMs may be closed).", ephemeral=True)

# (WarnReportedModal, TimeoutModal remain unchanged)

# ---------------------- View ----------------------

class ReportModerationView(ui.View):
    def __init__(self, *, report_id: int | None, reporter_id: int | None, reported_id: int | None,
                 ad_id: int | None, origin_guild_id: int | None, ad_jump: str | None):
        super().__init__(timeout=None)
        self.report_id = report_id
        self.reporter_id = reporter_id
        self.reported_id = reported_id
        self.ad_id = ad_id
        self.origin_guild_id = origin_guild_id
        self.ad_jump = ad_jump

    @ui.button(label="Ask Reporter", style=discord.ButtonStyle.secondary, custom_id="report:ask_reporter")
    async def ask_reporter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.report_id or not self.reporter_id:
            await interaction.response.send_message("Missing reporter context.", ephemeral=True)
            return
        try:
            reporter = interaction.client.get_user(self.reporter_id) or await interaction.client.fetch_user(self.reporter_id)
        except Exception:
            reporter = None
        if not reporter:
            await interaction.response.send_message("Reporter not found.", ephemeral=True)
            return
        await interaction.response.send_modal(AskReporterModal(self.report_id, reporter, interaction.channel_id))

# (Other buttons unchanged)

# ---------------------- Cog ----------------------

class Reports(commands.Cog):
    """Centralized ad reports (routes to main bot guild/category)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await reports_db.create_reports_table()
        await moderation_db.ensure_user_timeouts_schema()
        self.bot.add_view(ReportModerationView(
            report_id=None, reporter_id=None, reported_id=None, ad_id=None, origin_guild_id=None, ad_jump=None
        ))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Relay reporter DM replies back into the report channel."""
        if message.author.bot or message.guild:
            return
        try:
            link = await reports_db.get_open_conversation_by_reporter(message.author.id)
            if not link:
                return
            channel = self.bot.get_channel(link["channel_id"]) or await self.bot.fetch_channel(link["channel_id"])
            parts = [f"**Reply from <@{message.author.id}> on report `#{link['report_id']}`:**"]
            if message.content:
                parts.append(message.content)
            files = [await a.to_file() for a in message.attachments]
            await channel.send("\n".join(parts), files=files or None)
        except Exception:
            LOGGER.exception("Failed relaying reporter DM")

async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot), override=True)
