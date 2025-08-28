from __future__ import annotations

import asyncio
import logging
import os
import re
import traceback
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands, ui
from discord.ext import commands

from ..db import get_pool
import bot.db as db
from ..ui.dm_styles import send_pretty_interest_dm
from ..database import moderation_db, cooldowns_db

LOGGER = logging.getLogger("lfg_ads")
if not LOGGER.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s lfg_ads: %(message)s")
    h.setFormatter(fmt)
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

POST_TIMEOUT_SECONDS = int(os.getenv("LFG_POST_TIMEOUT_SECONDS", "60"))
USER_COOLDOWN_SEC = 5 * 60
MAX_SEND_CONCURRENCY = int(os.getenv("LFG_POST_MAX_CONCURRENCY", "5"))
PER_SEND_TIMEOUT = int(os.getenv("LFG_POST_PER_SEND_TIMEOUT", "8"))
SURFACE_ERROR_CODE = os.getenv("LFG_SURFACE_ERROR_CODE", "1") == "1"

AD_ID_RE = re.compile(r"Ad\s*#\s*(\d+)", re.IGNORECASE)

async def safe_ack(
    interaction: discord.Interaction,
    *,
    message: str | None = None,
    ephemeral: bool = True,
    use_thinking: bool = True,
) -> bool:
    try:
        if interaction.response.is_done():
            if message:
                try:
                    await interaction.followup.send(message, ephemeral=ephemeral)
                except (discord.NotFound, discord.HTTPException):
                    return False
            return True
        else:
            if message:
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.response.defer(ephemeral=ephemeral, thinking=use_thinking)
            return True
    except discord.InteractionResponded:
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        return False

def _err_code(prefix: str, exc: BaseException | None = None) -> str:
    if not SURFACE_ERROR_CODE:
        return ""
    typ = type(exc).__name__ if exc else ""
    return f" ({prefix}:{typ})" if typ else f" ({prefix})"

def _check_channel_perms(guild: discord.Guild, channel: discord.abc.GuildChannel) -> list[str]:
    me = guild.me
    if me is None:
        return ["bot member not resolved"]
    p = channel.permissions_for(me)
    missing = []
    if not p.view_channel:
        missing.append("view_channel")
    if not p.send_messages:
        missing.append("send_messages")
    if not p.embed_links:
        missing.append("embed_links")
    return missing

def _rel(ts: datetime | None) -> str:
    if not ts:
        return ""
    try:
        return f"<t:{int(ts.replace(tzinfo=timezone.utc).timestamp())}:R>"
    except Exception:
        return ts.isoformat()

def _extract_ad_id_from_message(msg: discord.Message | None) -> int | None:
    if not msg:
        return None
    try:
        for emb in msg.embeds or ():
            if emb.footer and emb.footer.text:
                m = AD_ID_RE.search(emb.footer.text)
                if m:
                    return int(m.group(1))
            if emb.title:
                m = AD_ID_RE.search(emb.title)
                if m:
                    return int(m.group(1))
            if emb.description:
                m = AD_ID_RE.search(emb.description)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return None

# --- tiny helper for 24h expiry ----------------------------------------------
def _is_msg_expired(msg: discord.Message | None, *, hours: int = 24) -> bool:
    if not msg or not msg.created_at:
        return False
    try:
        return msg.created_at + timedelta(hours=hours) <= datetime.now(timezone.utc)
    except Exception:
        return False
# -----------------------------------------------------------------------------


class ConnectButton(ui.View):
    """Persistent actions for an LFG ad."""
    def __init__(self, ad_id: int | None = None, *, timeout: float | None = None):
        super().__init__(timeout=timeout)  # None = persistent
        self.ad_id = ad_id

    @ui.button(label="I’m interested", style=discord.ButtonStyle.success, custom_id="lfg:connect")
    async def connect(self, interaction: discord.Interaction, button: ui.Button):
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=False)
        sent_followup = False
        try:
            # GLOBAL timeout gate first
            try:
                if await moderation_db.is_user_globally_timed_out(interaction.user.id):
                    until = await moderation_db.get_global_timeout_until(interaction.user.id)
                    if acked:
                        await interaction.followup.send(
                            f"You’re timed out from using the bot{f' until {_rel(until)}' if until else ''}.",
                            ephemeral=True,
                        )
                    return
            except Exception:
                LOGGER.exception("Global timeout check failed in ConnectButton.connect; allowing")

            # Per-guild gate (kept for compatibility)
            try:
                if interaction.guild and await moderation_db.is_user_timed_out(interaction.guild.id, interaction.user.id):
                    until = await moderation_db.get_timeout_until(interaction.guild.id, interaction.user.id)
                    if acked:
                        await interaction.followup.send(
                            f"You’re timed out from using the bot{f' until {_rel(until)}' if until else ''}.",
                            ephemeral=True,
                        )
                    return
            except Exception:
                LOGGER.exception("Per-guild timeout check failed in ConnectButton.connect; allowing")

            # 24h expiry gate
            if _is_msg_expired(interaction.message, hours=24):
                if acked and not sent_followup:
                    await interaction.followup.send(
                        "This LFG post has expired. Try a newer one!",
                        ephemeral=True,
                    )
                    sent_followup = True
                return

            # Resolve ad_id
            ad_id = self.ad_id or _extract_ad_id_from_message(interaction.message)
            if not ad_id:
                if acked and not sent_followup:
                    await interaction.followup.send(
                        "This ad can’t be identified anymore. It might be too old or malformed.",
                        ephemeral=True,
                    )
                return

            user = interaction.user
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            # Allow unlimited clicks (do not close ad)
            async with pool.acquire() as conn:
                ad = await conn.fetchrow(
                    """
                    SELECT id, author_id, author_name, game, platform, region, notes
                    FROM lfg_ads
                    WHERE id = $1
                    """,
                    int(ad_id),
                )
                await db.stats_inc("connections_made", 1)

            if not ad:
                if acked:
                    await interaction.followup.send(
                        "This ad no longer exists.",
                        ephemeral=True,
                    )
                    sent_followup = True
                return

            owner_id = int(ad["author_id"])
            owner_user = interaction.client.get_user(owner_id) or await interaction.client.fetch_user(owner_id)

            # DM the POSTER with full ad details + interested user (rich embed)
            if owner_user:
                try:
                    color_seed = (sum(ord(c) for c in (ad["game"] or "")) % 255)
                    color = discord.Color.from_rgb(255 - color_seed // 2, 120 + color_seed // 3, 80)

                    lines = [
                        "**Someone is interested in your ad!**",
                        "",
                        f"**Interested:** {user.mention}",
                        f"**Server:** {interaction.guild.name if interaction.guild else 'Unknown'}",
                        "",
                        f"**Game:** `{ad['game']}`",
                    ]
                    if ad["platform"]:
                        lines.append(f"**Platform:** `{ad['platform']}`")
                    if ad["region"]:
                        lines.append(f"**Region:** `{ad['region']}`")
                    if ad["notes"]:
                        lines.extend(["", f"**Notes:** {ad['notes']}"])

                    embed = discord.Embed(
                        title="Your LFG ad got a hit! ✨",
                        description="\n".join(lines),
                        color=color,
                        timestamp=datetime.utcnow(),
                    )

                    avatar = getattr(getattr(user, "display_avatar", None), "url", None)
                    if avatar:
                        embed.set_author(name=str(user), icon_url=avatar)
                        embed.set_thumbnail(url=avatar)

                    embed.set_footer(
                        text=f"Ad #{ad_id} • Powered by Matchmaker",
                        icon_url="https://i.imgur.com/4x9pIr0.png",
                    )

                    view = discord.ui.View()
                    if interaction.message:
                        view.add_item(discord.ui.Button(label="Open the ad", url=interaction.message.jump_url, emoji="🔗"))
                    view.add_item(
                        discord.ui.Button(
                            label="Message interested user",
                            url=f"discord://-/users/{user.id}",
                            emoji="✉️",
                        )
                    )

                    await owner_user.send(embed=embed, view=view)
                except Exception:
                    LOGGER.info("Owner DM failed; continuing", exc_info=True)

            # DM the CONNECTOR with mirrored details (now includes platform/region)
            try:
                await send_pretty_interest_dm(
                    recipient=user,
                    poster=owner_user,
                    ad_id=int(ad_id),
                    game=ad["game"],
                    platform=ad["platform"],
                    region=ad["region"],
                    notes=ad["notes"],
                    message_jump=interaction.message.jump_url if interaction.message else None,
                    guild=interaction.guild,
                )
            except Exception:
                LOGGER.info("Connector DM failed; continuing", exc_info=True)

            jump = None
            try:
                if interaction.message:
                    jump = interaction.message.jump_url
            except Exception:
                jump = None

            if acked:
                if jump:
                    await interaction.followup.send(
                        f"✅ I DM’d you both so you can coordinate. Have fun!\n"
                        f"Jump back to the ad: {jump}",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "✅ I DM’d you both so you can coordinate. Have fun!",
                        ephemeral=True,
                    )
                sent_followup = True

        except Exception as exc:
            LOGGER.error("ConnectButton.connect failed:\n%s", traceback.format_exc())
            if acked and not sent_followup:
                try:
                    await interaction.followup.send(
                        "Something went wrong while connecting. Try again." + _err_code("CONNECT", exc),
                        ephemeral=True,
                    )
                    sent_followup = True
                except Exception:
                    pass

    @ui.button(label="Report", style=discord.ButtonStyle.danger, custom_id="lfg:report")
    async def report(self, interaction: discord.Interaction, button: ui.Button):
        try:
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            ad_id = self.ad_id or _extract_ad_id_from_message(interaction.message)
            if not ad_id:
                await interaction.response.send_message("This ad can’t be identified anymore.", ephemeral=True)
                return

            async with pool.acquire() as conn:
                ad_row = await conn.fetchrow(
                    "SELECT id, author_id FROM lfg_ads WHERE id = $1",
                    int(ad_id),
                )
            if not ad_row:
                await interaction.response.send_message("This ad no longer exists.", ephemeral=True)
                return

            reported_id = int(ad_row["author_id"])

            reports_cog = interaction.client.get_cog("Reports")
            if not reports_cog or not hasattr(reports_cog, "open_report_modal"):
                await interaction.response.send_message("Reporting isn’t available right now. Try again later.", ephemeral=True)
                return

            await reports_cog.open_report_modal(interaction, reported_id=reported_id, ad_id=int(ad_id))

        except Exception:
            LOGGER.exception("Failed to open report modal")
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong while opening the report form.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong while opening the report form.", ephemeral=True)


class LfgAds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(ConnectButton(ad_id=None, timeout=None))
        try:
            await cooldowns_db.ensure_cooldowns_schema()
        except Exception:
            LOGGER.exception("Failed to ensure cooldowns table")

    lfg = app_commands.Group(name="lfg_ad", description="Create and manage LFG ads")

    @lfg.command(name="post", description="Post an LFG ad")
    @app_commands.guild_only()
    @app_commands.describe(
        game="The game you want to play",
        platform="PC/PS/Xbox/Switch/Mobile (optional)",
        region="NA/EU/APAC/Global (optional)",
        notes="Anything else people should know (optional)",
    )
    async def post(
        self,
        interaction: discord.Interaction,
        game: str,
        platform: str | None = None,
        region: str | None = None,
        notes: str | None = None,
    ):
        """
        Flow:
        - Send an immediate ephemeral "Posting your ad…" (visible, not a spinner)
        - Within a timeout, insert ad + broadcast to configured guild channels (concurrent with a cap)
        - Edit the original message to the final result (success or guidance)
        """
        # Send the initial message (so deploy interrupts don't leave a spinner)
        acked = await safe_ack(interaction, message="Posting your ad…", ephemeral=True, use_thinking=False)
        if not acked:
            return

        async def do_post_work() -> int:
            """Insert the ad, broadcast it, and return the number of servers posted to."""
            # --- DB INSERT + SETTINGS FETCH ---
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            try:
                async with pool.acquire() as conn:
                    ad_id = await conn.fetchval(
                        """
                        INSERT INTO lfg_ads (author_id, author_name, game, platform, region, notes, status)
                        VALUES ($1, $2, $3, $4, $5, $6, 'open') RETURNING id
                        """,
                        int(interaction.user.id),
                        str(interaction.user),
                        game,
                        platform,
                        region,
                        notes,
                    )
            except Exception as exc:
                LOGGER.error("DB insert failed:\n%s", traceback.format_exc())
                raise RuntimeError("DB_INSERT") from exc

            try:
                title_bits: list[str] = [game]
                if platform:
                    title_bits.append(f"• {platform}")
                if region:
                    title_bits.append(f"• {region}")

                embed = discord.Embed(
                    title=" ".join(title_bits),
                    description=notes or "Looking for teammates!",
                    color=discord.Color.blurple(),
                )
                embed.set_author(
                    name=str(interaction.user),
                    icon_url=interaction.user.display_avatar.url,
                )
                embed.set_footer(text=f"Posted by {interaction.user} • Ad #{ad_id}")

                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT guild_id, lfg_channel_id FROM guild_settings WHERE lfg_channel_id IS NOT NULL"
                    )
            except Exception as exc:
                LOGGER.error("Building embed or guild settings query failed:\n%s", traceback.format_exc())
                raise RuntimeError("GUILD_QUERY") from exc

            # --- BROADCAST (CONCURRENT WITH CAP) ---
            view = ConnectButton(ad_id=ad_id)
            sem = asyncio.Semaphore(MAX_SEND_CONCURRENCY)
            posted_count = 0

            async def send_one(guild_id: int, channel_id: int) -> bool:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return False
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.TextChannel):
                    return False
                async with sem:
                    try:
                        await asyncio.wait_for(channel.send(embed=embed, view=view), timeout=PER_SEND_TIMEOUT)
                        return True
                    except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError) as exc:
                        LOGGER.info("Send to %s#%s failed: %r", guild.name if guild else guild_id, channel_id, exc)
                        return False

            tasks = [
                asyncio.create_task(send_one(int(r["guild_id"]), int(r["lfg_channel_id"])))
                for r in rows
            ]

            for coro in asyncio.as_completed(tasks):
                ok = await coro
                if ok:
                    posted_count += 1

            return posted_count

        try:
            posted = await asyncio.wait_for(do_post_work(), timeout=POST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            LOGGER.warning("post() timed out after %ss", POST_TIMEOUT_SECONDS)
            try:
                await interaction.edit_original_response(
                    content="⏳ Timed out while posting your ad. Please try again." + _err_code("TIMEOUT")
                )
            except Exception:
                pass
            return
        except Exception as exc:
            # Any error inside do_post_work gets logged there; we surface a short code here.
            try:
                await interaction.edit_original_response(
                    content="Something went wrong while posting your ad. Please try again." + _err_code("POST", exc)
                )
            except Exception:
                pass
            return

        # Build and send the final result (edit the original message)
        try:
            if posted == 0:
                await interaction.edit_original_response(
                    content=(
                        "Your ad was saved, but no servers have an LFG channel configured yet.\n"
                        "Ask server owners to run `/lfg_channel set #channel`."
                    )
                )
            else:
                await interaction.edit_original_response(
                    content=(
                        "✅ Your ad was posted!"
                        f"\n• **Servers posted to:** {posted}"
                    )
                )
        except (discord.NotFound, discord.HTTPException):
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
