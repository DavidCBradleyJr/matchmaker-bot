# bot/cogs/lfg_ads.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("lfg_ads")

# ---- Config ---------------------------------------------------------------

STATUS_DEFAULT = "open"  # change to "active" if you drop 'open' later
SITE_URL = "https://matchmaker.gg"  # branding + link button target

PLATFORM_COLORS = {
    "pc": 0x5865F2,        # Discord blurple
    "xbox": 0x107C10,
    "playstation": 0x003791,
    "ps": 0x003791,
    "switch": 0xE60012,
    "mobile": 0x00A3FF,
    "other": 0x2B2D31,
}

PLATFORM_EMOJIS = {
    "pc": "🖥️",
    "xbox": "🟩",
    "playstation": "🟦",
    "ps": "🟦",
    "switch": "🔴",
    "mobile": "📱",
    "other": "🎮",
}

# ---- Helpers --------------------------------------------------------------

def _platform_color(platform: str | None) -> int:
    if not platform:
        return PLATFORM_COLORS["other"]
    return PLATFORM_COLORS.get(platform.lower(), PLATFORM_COLORS["other"])

def _platform_emoji(platform: str | None) -> str:
    if not platform:
        return PLATFORM_EMOJIS["other"]
    return PLATFORM_EMOJIS.get(platform.lower(), PLATFORM_EMOJIS["other"])

def _safe(s: Optional[str], dash: str = "—") -> str:
    s = (s or "").strip()
    return s if s else dash

def _trim_notes(notes: Optional[str], limit: int = 300) -> Optional[str]:
    if not notes:
        return None
    n = notes.strip()
    if not n:
        return None
    if len(n) > limit:
        return n[: limit - 1] + "…"
    return n

@dataclass
class CreatedAd:
    id: int
    message_id: int
    channel_id: int
    guild_id: int


# ---- Embed & View ---------------------------------------------------------

def build_ad_embed(
    *,
    author: discord.abc.User,
    game: str,
    platform: Optional[str],
    region: Optional[str],
    notes: Optional[str],
    guild_icon_url: Optional[str],
    site_url: str = SITE_URL,
) -> discord.Embed:
    color = _platform_color(platform)
    pfx = _platform_emoji(platform)
    title = f"{pfx} {_safe(game)} • {_safe((platform or '').title(), dash='—')}"

    desc_lines: list[str] = []
    # Tiny, subtle credit (kept in body so it's clickable)
    desc_lines.append(f"*Powered by [Matchmaker]({site_url})*")

    embed = discord.Embed(
        title=title,
        description="\n".join(desc_lines),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    avatar = getattr(author, "display_avatar", None)
    if avatar:
        embed.set_author(
            name=f"{author.display_name} is looking for a squad",
            icon_url=author.display_avatar.url,
        )
    else:
        embed.set_author(name=f"{author.display_name} is looking for a squad")

    embed.add_field(name="Region", value=_safe(region), inline=True)

    trimmed = _trim_notes(notes)
    if trimmed:
        embed.add_field(name="Notes", value=trimmed, inline=False)

    if guild_icon_url:
        embed.set_footer(text="Matchmaker • Find teammates fast", icon_url=guild_icon_url)
    else:
        embed.set_footer(text="Matchmaker • Find teammates fast")

    return embed


class AdActionView(discord.ui.View):
    def __init__(self, *, ad_id: int, site_url: str = SITE_URL, timeout: Optional[float] = 1800):
        super().__init__(timeout=timeout)
        self.ad_id = ad_id
        self.site_url = site_url

        # Primary connect button
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="I’m interested",
            custom_id=f"ad_connect:{ad_id}",
            emoji="🤝",
        ))

        # Optional: view on website
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="View on Web",
            url=f"{self.site_url}/ads/{ad_id}",
        ))

        # Optional: report
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Report",
            custom_id=f"ad_report:{ad_id}",
            emoji="🚩",
        ))


# ---- DB access (matches your schema) -------------------------------------

async def _fetch_lfg_channel_id(conn: asyncpg.Connection, guild_id: int) -> Optional[int]:
    row = await conn.fetchrow(
        "SELECT lfg_channel_id FROM guild_settings WHERE guild_id = $1",
        guild_id,
    )
    return int(row["lfg_channel_id"]) if row and row["lfg_channel_id"] else None


async def _insert_lfg_ad(
    conn: asyncpg.Connection,
    *,
    author_id: int,
    author_name: Optional[str],
    game: str,
    platform: Optional[str],
    region: Optional[str],
    notes: Optional[str],
    status: str,
) -> int:
    """
    INSERT INTO lfg_ads and return new ad id.
    Columns per schema:
      id BIGSERIAL PK,
      author_id BIGINT NOT NULL,
      author_name TEXT,
      game TEXT NOT NULL,
      platform TEXT,
      region TEXT,
      notes TEXT,
      status ad_status NOT NULL DEFAULT 'active' (you set to 'open'),
      created_at TIMESTAMPTZ DEFAULT NOW()
    """
    return await conn.fetchval(
        """
        INSERT INTO lfg_ads (
            author_id, author_name, game, platform, region, notes, status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::ad_status)
        RETURNING id
        """,
        author_id, author_name, game, platform, region, notes, status,
    )


async def _insert_lfg_post(
    conn: asyncpg.Connection,
    *,
    ad_id: int,
    guild_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    """
    INSERT INTO lfg_posts (ad_id, guild_id, channel_id, message_id)
    PK (ad_id, guild_id)
    """
    await conn.execute(
        """
        INSERT INTO lfg_posts (ad_id, guild_id, channel_id, message_id)
        VALUES ($1, $2, $3, $4)
        """,
        ad_id, guild_id, channel_id, message_id,
    )


async def _upsert_guild_channel(
    conn: asyncpg.Connection,
    *,
    guild_id: int,
    channel_id: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO guild_settings (guild_id, lfg_channel_id)
        VALUES ($1, $2)
        ON CONFLICT (guild_id)
        DO UPDATE SET lfg_channel_id = EXCLUDED.lfg_channel_id,
                      updated_at = NOW()
        """,
        guild_id, channel_id,
    )


# ---- Slash command Cog ----------------------------------------------------

class LFGAds(commands.Cog):
    """LFG ads: create and broadcast clean, branded posts with action buttons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    lfg = app_commands.Group(name="lfg", description="Find teammates fast.")

    @lfg.command(name="post", description="Post an LFG ad to your server’s LFG channel.")
    @app_commands.describe(
        game="What game are you playing?",
        platform="PC, Xbox, PlayStation, Switch, Mobile, etc. (optional)",
        region="NA/EU/Asia or a timezone/region name (optional)",
        notes="Anything else teammates should know (optional)",
    )
    async def post(
        self,
        interaction: discord.Interaction,
        game: str,
        platform: Optional[str] = None,
        region: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not interaction.guild:
            return await interaction.followup.send("This command must be used in a server.", ephemeral=True)

        pool: asyncpg.Pool = getattr(self.bot, "db_pool", None)
        if pool is None:
            log.error("Database pool missing on bot.")
            return await interaction.followup.send("DB connection not available. Try again later.", ephemeral=True)

        # Resolve target channel from DB
        try:
            async with pool.acquire() as conn:
                channel_id = await _fetch_lfg_channel_id(conn, interaction.guild.id)
        except Exception as e:
            log.exception("Failed to fetch LFG channel: %s", e)
            return await interaction.followup.send("Couldn’t find the LFG channel for this server.", ephemeral=True)

        if not channel_id:
            return await interaction.followup.send(
                "No LFG channel is configured for this server yet. Ask an admin to run `/lfg set_channel`.",
                ephemeral=True,
            )

        # Ensure we have a live channel object
        target_channel = interaction.guild.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            return await interaction.followup.send("Configured LFG channel is not a text channel.", ephemeral=True)

        # Build embed & view
        guild_icon_url = getattr(interaction.guild.icon, "url", None) if interaction.guild.icon else None
        embed = build_ad_embed(
            author=interaction.user,
            game=game,
            platform=platform,
            region=region,
            notes=notes,
            guild_icon_url=guild_icon_url,
            site_url=SITE_URL,
        )

        # Insert ad → send message → record lfg_posts
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    ad_id = await _insert_lfg_ad(
                        conn,
                        author_id=interaction.user.id,
                        author_name=interaction.user.display_name,
                        game=game,
                        platform=platform,
                        region=region,
                        notes=notes,
                        status=STATUS_DEFAULT,  # 'open' per your ALTER; flip to 'active' if you undo it
                    )

            # Send the message (need message_id for lfg_posts)
            temp_view = AdActionView(ad_id=0, site_url=SITE_URL)
            sent = await target_channel.send(embed=embed, view=temp_view)

            # Now persist lfg_posts and update the buttons with the real ad_id
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _insert_lfg_post(
                        conn,
                        ad_id=ad_id,
                        guild_id=interaction.guild.id,
                        channel_id=sent.channel.id,
                        message_id=sent.id,
                    )

            new_view = AdActionView(ad_id=ad_id, site_url=SITE_URL)
            await sent.edit(view=new_view)

            await interaction.followup.send(
                f"Your ad is live in {sent.channel.mention}! (Ad #{ad_id})",
                ephemeral=True,
            )

        except asyncpg.PostgresError as db_err:
            log.error("DB operation failed:", exc_info=db_err)
            # Best effort: remove the orphaned message if it was sent
            try:
                if 'sent' in locals():
                    await sent.delete()
            except Exception:
                pass
            return await interaction.followup.send(
                "Something went wrong while posting your ad. Please try again.",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("Unexpected error sending ad: %s", e)
            try:
                if 'sent' in locals():
                    await sent.delete()
            except Exception:
                pass
            return await interaction.followup.send(
                "Something went wrong while posting your ad. Please try again.",
                ephemeral=True,
            )

    # Admin: set the per-guild LFG channel in guild_settings.lfg_channel_id
    @lfg.command(name="set_channel", description="(Admin) Set the channel used for LFG ads.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="Pick the LFG ad channel")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("This command must be used in a server.", ephemeral=True)

        pool: asyncpg.Pool = getattr(self.bot, "db_pool", None)
        if pool is None:
            return await interaction.followup.send("DB connection not available.", ephemeral=True)

        try:
            async with pool.acquire() as conn:
                await _upsert_guild_channel(conn, guild_id=interaction.guild.id, channel_id=channel.id)
        except Exception as e:
            log.exception("Failed to set LFG channel: %s", e)
            return await interaction.followup.send("Couldn’t save the LFG channel.", ephemeral=True)

        await interaction.followup.send(f"LFG channel set to {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LFGAds(bot))
