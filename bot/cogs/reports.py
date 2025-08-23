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

class AskReporterModal(ui.Modal, title="Ask Reporter for More Info"):
    def __init__(self, target: discord.User):
        super().__init__(timeout=180)
        self.target = target
        self.message = ui.TextInput(label="Message to reporter", max_length=300, required=True)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.target.send(
                f"👋 A moderator has asked for more info about your report:\n> {self.message.value}"
            )
            await interaction.response.send_message("✅ DM sent to reporter.", ephemeral=True)
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
    def __init__(self, reported_id: int):
        super().__init__(timeout=180)
        self.reported_id = int(reported_id)
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

        try:
            await moderation_db.ensure_user_timeouts_schema()

            now = datetime.now(timezone.utc)
            until = now + (timedelta(minutes=mins) if mins > 0 else timedelta(days=36500))

            await moderation_db.add_timeout(
                interaction.guild.id,
                self.reported_id,
                until,
                created_by=interaction.user.id,
                reason=str(self.reason.value).strip(),
            )

            u = interaction.client.get_user(self.reported_id) or await interaction.client.fetch_user(self.reported_id)
            try:
                if u:
                    if mins > 0:
                        await u.send(f"⏱ You’ve been timed out from using the bot for **{mins} minutes**.\nReason: {self.reason.value}")
                    else:
                        await u.send(f"⏱ You’ve been timed out from using the bot **indefinitely**.\nReason: {self.reason.value}")
            except Exception:
                LOGGER.info("Reported user DM after timeout failed")

            await interaction.response.send_message("✅ Timeout recorded.", ephemeral=True)

            try:
                if isinstance(interaction.channel, discord.TextChannel):
                    await interaction.channel.send(
                        f"⏱ **Timeout applied** to `<@{self.reported_id}>` by {interaction.user.mention}."
                    )
            except Exception:
                pass

        except Exception as exc:
            LOGGER.exception("Timeout DB write failed")
            diag = f"\n\nDebug: {type(exc).__name__}: {str(exc)[:180]}" if (isinstance(interaction.user, discord.Member) and _is_mod(interaction.user)) else ""
            base = ("Failed to store timeout. Try again."
                    " If this keeps happening, verify the app’s DATABASE_URL points to the DB you migrated"
                    " and that the DB role can INSERT (DDL optional).")
            if not interaction.response.is_done():
                await interaction.response.send_message(base + diag, ephemeral=True)
            else:
                await interaction.followup.send(base + diag, ephemeral=True)

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
        if interaction.guild_id != MAIN_BOT_GUILD_ID or not isinstance(interaction.user, discord.Member) or not _is_mod(interaction.user):
            await interaction.response.send_message("You don’t have permission to use these controls.", ephemeral=True)
            return False
        return True

    @ui.button(label="Ask Reporter", style=discord.ButtonStyle.secondary, custom_id="report:ask_reporter")
    async def ask_reporter(self, interaction: discord.Interaction, button: ui.Button):
        reporter_user = interaction.client.get_user(self.reporter_id or 0) if self.reporter_id else None
        if not reporter_user:
            await interaction.response.send_message("Reporter not cached; try again later.", ephemeral=True)
            return
        await interaction.response.send_modal(AskReporterModal(reporter_user))

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
        if not target_id:
            await interaction.response.send_message("Can’t identify the reported user on this message.", ephemeral=True)
            return
        await interaction.response.send_modal(TimeoutModal(int(target_id)))

    @ui.button(label="Resolve / Close", style=discord.ButtonStyle.success, custom_id="report:resolve")
    async def resolve_close(self, interaction: discord.Interaction, button: ui.Button):
        ctx = _parse_ctx_from_message(interaction.message)
        rid = ctx["report_id"] or self.report_id
        try:
            if rid:
                await reports_db.close_report(int(rid), closed_by=interaction.user.id)
        except Exception:
            LOGGER.exception("Failed to mark report closed in DB")

        try:
            channel = interaction.channel
            if isinstance(channel, discord.TextChannel):
                name = channel.name
                if not name.startswith("resolved-"):
                    await channel.edit(name=f"resolved-{name}", reason=f"Report #{rid or '?'} resolved")

                # lock sends + threads
                ow = channel.overwrites

                def _deny_send_like(po: discord.PermissionOverwrite) -> discord.PermissionOverwrite:
                    po.send_messages = False
                    po.send_messages_in_threads = False
                    po.create_public_threads = False
                    po.create_private_threads = False
                    return po

                # @everyone
                po = ow.get(channel.guild.default_role, discord.PermissionOverwrite())
                ow[channel.guild.default_role] = _deny_send_like(po)

                # any role that already has an overwrite -> deny sends
                for target, po in list(ow.items()):
                    if isinstance(target, discord.Role):
                        po = po or discord.PermissionOverwrite()
                        ow[target] = _deny_send_like(po)

                await channel.edit(overwrites=ow, reason=f"Report #{rid or '?'} closed")

            await interaction.response.send_message("✅ Report closed and channel locked.", ephemeral=True)

            try:
                await channel.send(f"🟢 **Resolved by** {interaction.user.mention} — report #{rid or '?'}")
            except Exception:
                pass

        except Exception:
            LOGGER.exception("Failed to lock/rename channel on resolve")
            if not interaction.response.is_done():
                await interaction.response.send_message("Tried to close, but an error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("Tried to close, but an error occurred.", ephemeral=True)

class AdReportModal(ui.Modal, title="Report this ad"):
    def __init__(self, parent: "Reports", *, reporter: discord.User, reported_id: int, ad_id: int, ad_message_id: int, origin_guild_id: int):
        super().__init__(timeout=180)
        self.parent = parent
        self.reporter = reporter
        self.reported_id = int(reported_id)
        self.ad_id = int(ad_id)
        self.ad_message_id = int(ad_message_id)
        self.origin_guild_id = int(origin_guild_id)

        self.description = ui.TextInput(
            label="What’s wrong? (max 120 chars)",
            style=discord.TextStyle.short,
            max_length=MAX_DESC,
            required=True,
            placeholder="Spam, harassment, false info…"
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        desc = str(self.description.value).strip()
        try:
            report_id, total_reports = await reports_db.insert_report(
                origin_guild_id=self.origin_guild_id,
                reporter_id=int(self.reporter.id),
                reported_id=self.reported_id,
                ad_id=self.ad_id,
                ad_message_id=self.ad_message_id,
                description=desc,
            )

            main_guild = interaction.client.get_guild(MAIN_BOT_GUILD_ID)
            if not main_guild:
                main_guild = await interaction.client.fetch_guild(MAIN_BOT_GUILD_ID)

            category = main_guild.get_channel(REPORTS_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                raise RuntimeError("REPORTS_CATEGORY_ID does not point to a Category in the main bot guild.")

            reporter_slug = _slug_name(self.reporter.name)
            chan_name = f"report-{report_id}-{reporter_slug}"

            channel = await main_guild.create_text_channel(
                name=chan_name,
                category=category,
                reason=f"Ad report #{report_id}",
                topic=f"Ad report #{report_id} • From guild {self.origin_guild_id} • Ad #{self.ad_id}",
            )

            reported_user = interaction.client.get_user(self.reported_id) or await interaction.client.fetch_user(self.reported_id)
            reporter_user = self.reporter

            embed = discord.Embed(
                title=f"Ad Report #{report_id}",
                description=desc,
                color=discord.Color.red(),
            )
            embed.add_field(name="Reporter", value=f"{reporter_user.mention} (`{reporter_user.id}`)", inline=True)
            embed.add_field(name="Reported", value=f"{reported_user.mention if reported_user else self.reported_id} (`{self.reported_id}`)", inline=True)
            embed.add_field(name="Ad", value=f"ID: `{self.ad_id}`", inline=True)
            embed.add_field(name="Reports against user", value=f"{total_reports} total (includes this report)", inline=True)

            jump = None
            try:
                if interaction.message:
                    jump = interaction.message.jump_url
            except Exception:
                pass
            if jump:
                embed.add_field(name="Original Message", value=f"[Jump to message]({jump})", inline=False)

            await reports_db.create_reports_table()
            await moderation_db.ensure_user_timeouts_schema()

            await channel.send(
                embed=embed,
                view=ReportModerationView(
                    report_id=report_id,
                    reporter_id=reporter_user.id,
                    reported_id=self.reported_id,
                    ad_id=self.ad_id,
                    origin_guild_id=self.origin_guild_id,
                    ad_jump=jump,
                ),
            )

            await interaction.response.send_message(
                f"✅ Thanks, your report was filed as **#{report_id}**.", ephemeral=True
            )
        except Exception:
            LOGGER.exception("Failed to submit ad report")
            if not interaction.response.is_done():
                await interaction.response.send_message("Something went wrong while filing your report. Please try again.", ephemeral=True)
            else:
                await interaction.followup.send("Something went wrong while filing your report. Please try again.", ephemeral=True)

class Reports(commands.Cog):
    """Centralized ad reports (routes to main bot guild/category)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await reports_db.create_reports_table()
        await moderation_db.ensure_user_timeouts_schema()
        # persistent handler so old messages keep working
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot), override=True)
