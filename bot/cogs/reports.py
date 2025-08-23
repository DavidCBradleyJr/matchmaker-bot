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
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
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
            # Open conversation bridge so replies route to this channel
            await reports_db.create_reports_table()
            await reports_db.open_conversation(self.report_id, self.reporter.id, self.channel_id)
            await interaction.response.send_message("✅ DM sent to reporter. Their replies will show up here.", ephemeral=True)
        except Exception:
            LOGGER.exception("DM to reporter failed")
            await interaction.response.send_message("Couldn’t DM the reporter (DMs may be closed).", ephemeral=True)

class WarnReportedModal(ui.Modal, title="Warn Reported User"):
    def __init__(self, target: discord.User):
        super().__init__(timeout=180)
        self.reason = ui.TextInput(label="Reason", max_length=300, required=True, placeholder="Short reason shown in DM")
        self.target = target
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.target.send(f"⚠️ You’ve received a warning from the moderators:\n> {self.reason.value}")
            await interaction.response.send_message("✅ Warning DM sent to the reported user.", ephemeral=True)
        except Exception:
            LOGGER.exception("DM to reported failed")
            await interaction.response.send_message("Couldn’t DM the user (DMs may be closed).", ephemeral=True)

class TimeoutModal(ui.Modal, title="Timeout Reported User"):
    def __init__(self, reported_id: int, origin_guild_id: int | None):
        super().__init__(timeout=180)
        self.reported_id = int(reported_id)
        self.origin_guild_id = int(origin_guild_id) if origin_guild_id else None
        self.minutes = ui.TextInput(
            label="Duration (minutes, 0 = indefinite)",
            required=True,
            max_length=6,
            placeholder="e.g., 60 for 1 hour"
        )
        self.reason = ui.TextInput(label="Reason", required=True, max_length=300, placeholder="Short reason")
        self.add_item(self.minutes)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            mins = max(0, int(str(self.minutes.value).strip()))
        except ValueError:
            await interaction.response.send_message("Enter a valid number of minutes.", ephemeral=True)
            return

        ctx_gid = self.origin_guild_id
        if not ctx_gid:
            ctx = _parse_ctx_from_message(interaction.message)
            ctx_gid = ctx["origin_guild_id"] or (interaction.guild.id if interaction.guild else None)
        if not ctx_gid:
            await interaction.response.send_message("Couldn’t identify the origin server for this report.", ephemeral=True)
            return

        try:
            await moderation_db.ensure_user_timeouts_schema()
            now = datetime.now(timezone.utc)
            until = now + (timedelta(minutes=mins) if mins > 0 else timedelta(days=36500))
            await moderation_db.add_timeout(
                int(ctx_gid), self.reported_id, until,
                created_by=interaction.user.id, reason=str(self.reason.value).strip(),
            )

            u = interaction.client.get_user(self.reported_id) or await interaction.client.fetch_user(self.reported_id)
            try:
                if u:
                    if mins > 0:
                        await u.send(f"⏱ You’ve been timed out from using the bot for **{mins} minutes** in that server.\nReason: {self.reason.value}")
                    else:
                        await u.send(f"⏱ You’ve been timed out from using the bot **indefinitely** in that server.\nReason: {self.reason.value}")
            except Exception:
                LOGGER.info("Reported user DM after timeout failed")

            await interaction.response.send_message("✅ Timeout recorded.", ephemeral=True)

            try:
                if isinstance(interaction.channel, discord.TextChannel):
                    await interaction.channel.send(
                        f"⏱ **Timeout applied** to `<@{self.reported_id}>` by {interaction.user.mention} (server `{ctx_gid}`)."
                    )
            except Exception:
                pass

        except Exception:
            LOGGER.exception("Timeout DB write failed")
            base = ("Failed to store timeout. Try again."
                    " If this keeps happening, verify DATABASE_URL and DB permissions.")
            if not interaction.response.is_done():
                await interaction.response.send_message(base, ephemeral=True)
            else:
                await interaction.followup.send(base, ephemeral=True)

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only mods in main bot guild can use these controls
        if interaction.guild_id != MAIN_BOT_GUILD_ID or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("You don’t have permission to use these controls.", ephemeral=True)
            return False
        if not _is_mod(interaction.user):
            await interaction.response.send_message("You don’t have permission to use these controls.", ephemeral=True)
            return False
        return True

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

    @ui.button(label="Warn Reported", style=discord.ButtonStyle.primary, custom_id="report:warn_reported")
    async def warn_reported(self, interaction: discord.Interaction, button: ui.Button):
        ctx = _parse_ctx_from_message(interaction.message)
        target_id = ctx["reported_id"] or self.reported_id
        if not target_id:
            await interaction.response.send_message("Can’t identify the reported user on this message.", ephemeral=True)
            return
        user = interaction.client.get_user(int(target_id)) or await interaction.client.fetch_user(int(target_id))
        if not user:
            await interaction.response.send_message("User not found.", ephemeral=True)
            return
        await interaction.response.send_modal(WarnReportedModal(user))

    @ui.button(label="Timeout Reported", style=discord.ButtonStyle.danger, custom_id="report:timeout")
    async def timeout_reported(self, interaction: discord.Interaction, button: ui.Button):
        ctx = _parse_ctx_from_message(interaction.message)
        target_id = ctx["reported_id"] or self.reported_id
        ogid = ctx["origin_guild_id"] or self.origin_guild_id
        if not target_id:
            await interaction.response.send_message("Can’t identify which user to timeout.", ephemeral=True)
            return
        if not ogid:
            await interaction.response.send_message("Can’t identify which server to apply the timeout to.", ephemeral=True)
            return
        await interaction.response.send_modal(TimeoutModal(int(target_id), int(ogid)))

    @ui.button(label="Past Reports", style=discord.ButtonStyle.secondary, custom_id="report:history")
    async def history(self, interaction: discord.Interaction, button: ui.Button):
        ctx = _parse_ctx_from_message(interaction.message)
        target_id = ctx["reported_id"] or self.reported_id
        if not target_id:
            await interaction.response.send_message("Can’t identify the reported user on this message.", ephemeral=True)
            return
        try:
            total = await reports_db.get_report_count_for_user(int(target_id))
            rows = await reports_db.fetch_recent_reports_by_reported(int(target_id), limit=10)
            if total == 0:
                await interaction.response.send_message("No prior reports for this user.", ephemeral=True)
                return
            emb = discord.Embed(
                title=f"Past reports for `{target_id}`",
                description=f"Total reports: **{total}** (showing up to 10 most recent)",
                color=discord.Color.orange(),
            )
            if rows:
                lines = []
                for r in rows:
                    ts = int(r["created_at"].timestamp()) if r["created_at"] else None
                    when = f"<t:{ts}:R>" if ts else "unknown time"
                    desc = (r["description"] or "").strip()
                    if len(desc) > 80:
                        desc = desc[:77] + "…"
                    lines.append(f"• **#{r['id']}** — {when} — ad `{r['ad_id']}` — by `{r['reporter_id']}`\n  {desc}")
                emb.add_field(name="Recent", value="\n".join(lines), inline=False)
            await interaction.response.send_message(embed=emb, ephemeral=True)
        except Exception:
            LOGGER.exception("Past reports lookup failed")
            await interaction.response.send_message("Couldn’t fetch prior reports right now.", ephemeral=True)

    @ui.button(label="Resolve / Close", style=discord.ButtonStyle.success, custom_id="report:resolve")
    async def resolve_close(self, interaction: discord.Interaction, button: ui.Button):
        ctx = _parse_ctx_from_message(interaction.message)
        rid = ctx["report_id"] or self.report_id

        # Mark closed in DB (best-effort)
        try:
            if rid:
                await reports_db.close_report(int(rid), closed_by=interaction.user.id)
        except Exception:
            LOGGER.exception("Failed to mark report closed in DB")

        # Delete the channel (no archiving)
        try:
            ch = interaction.channel
            if not isinstance(ch, discord.TextChannel):
                await interaction.response.send_message("✅ Report marked resolved.", ephemeral=True)
                return

            me = ch.guild.me
            perms = ch.permissions_for(me)
            if not perms.manage_channels:
                msg = "I need the `Manage Channels` permission to delete this report channel."
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return

            if not interaction.response.is_done():
                await interaction.response.send_message("✅ Report closed. Deleting this channel…", ephemeral=True)
            else:
                await interaction.followup.send("✅ Report closed. Deleting this channel…", ephemeral=True)

            await ch.delete(reason=f"Report #{rid or '?'} resolved and deleted by {interaction.user}")
        except Exception:
            LOGGER.exception("Resolve/delete flow failed (guild=%s ch=%s)", getattr(interaction.guild, "id", "?"), getattr(interaction.channel, "id", "?"))
            if not interaction.response.is_done():
                await interaction.response.send_message("Tried to close, but an error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("Tried to close, but an error occurred.", ephemeral=True)

# ---------------------- Cog ----------------------

class Reports(commands.Cog):
    """Centralized ad reports (routes to main bot guild/category)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Ensure tables on cog load (safe if called multiple times)
        try:
            await reports_db.create_reports_table()
        except Exception:
            LOGGER.exception("Failed to ensure reports tables on cog load")
        await moderation_db.ensure_user_timeouts_schema()
        self.bot.add_view(ReportModerationView(
            report_id=None, reporter_id=None, reported_id=None, ad_id=None, origin_guild_id=None, ad_jump=None
        ))

    async def open_report_modal(self, interaction: discord.Interaction, *, reported_id: int, ad_id: int) -> None:
        if not MAIN_BOT_GUILD_ID or not REPORTS_CATEGORY_ID:
            await interaction.response.send_message(
                "Reporting isn’t configured yet. (Missing MAIN_BOT_GUILD_ID / REPORTS_CATEGORY_ID)", ephemeral=True
            )
            return
        ad_message_id = interaction.message.id if interaction.message else 0
        origin_guild_id = interaction.guild_id or 0
        modal = AdReportModal(
            self,
            reporter=interaction.user,
            reported_id=reported_id,
            ad_id=ad_id,
            ad_message_id=ad_message_id,
            origin_guild_id=origin_guild_id,
        )
        await interaction.response.send_modal(modal)

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
