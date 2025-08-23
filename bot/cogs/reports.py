from __future__ import annotations

import os
import re
import logging
import discord
from discord import ui
from discord.ext import commands

from ..database import reports_db

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
MAX_DESC = 120

def _slug_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")[:24] or "user"

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
            report_id = await reports_db.insert_report(
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

            jump = None
            try:
                if interaction.message:
                    jump = interaction.message.jump_url
            except Exception:
                pass
            if jump:
                embed.add_field(name="Original Message", value=f"[Jump to message]({jump})", inline=False)

            await channel.send(embed=embed)

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
