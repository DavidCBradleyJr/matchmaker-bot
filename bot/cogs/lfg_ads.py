from __future__ import annotations

import asyncio
import logging
import os
import traceback
from time import monotonic

import discord
from discord import app_commands, ui
from discord.ext import commands

from ..db import get_pool
import bot.db as db
from ..database import moderation_db

from ..ui.dm_styles import send_pretty_interest_dm  # import the helper

# ---------------------
# Logging
# ---------------------

LOGGER = logging.getLogger("lfg_ads")
if not LOGGER.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(levelname)s:lfg_ads:%(message)s"))
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

# ---------------------
# Config
# ---------------------

POST_TIMEOUT_SECONDS = int(os.getenv("LFG_POST_TIMEOUT_SECONDS", "60"))
USER_COOLDOWN_SEC = 5 * 60  # 1 post per user per 5 minutes
MAX_SEND_CONCURRENCY = int(os.getenv("LFG_POST_MAX_CONCURRENCY", "5"))
PER_SEND_TIMEOUT = int(os.getenv("LFG_POST_PER_SEND_TIMEOUT", "8"))
SURFACE_ERROR_CODE = os.getenv("LFG_SURFACE_ERROR_CODE", "1") == "1"

# ---------------------
# Utilities
# ---------------------

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
                except Exception:
                    return False
            return True
        if message:
            await interaction.response.send_message(message, ephemeral=ephemeral)
        elif use_thinking:
            await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        else:
            await interaction.response.defer(ephemeral=ephemeral)
        return True
    except Exception:
        return False


class ConnectButton(ui.View):
    def __init__(self, *, ad_id: int, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.ad_id = ad_id

    @ui.button(label="I’m interested", style=discord.ButtonStyle.success, custom_id="lfg:connect")
    async def connect(self, interaction: discord.Interaction, button: ui.Button):
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=False)
        sent_followup = False
        try:
            user = interaction.user
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT author_id, author_name, game, platform, region, notes FROM lfg_ads WHERE id=$1",
                    int(self.ad_id),
                )

            if not row:
                await interaction.followup.send("This ad no longer exists.", ephemeral=True)
                return

            # DM both parties (helper formats the DM)
            await send_pretty_interest_dm(
                interactor=user,
                ad_author_id=int(row["author_id"]),
                ad_author_name=str(row["author_name"]),
                game=str(row["game"]),
                platform=row["platform"],
                region=row["region"],
                notes=row["notes"],
            )
            sent_followup = True
            await interaction.followup.send("✅ I’ve DMed you and the ad author to connect you.", ephemeral=True)

        except Exception:
            LOGGER.exception("Failed to process interest click")
            if not sent_followup:
                msg = "Something went wrong trying to connect you. Please try again."
                if SURFACE_ERROR_CODE:
                    msg += " (CONNECT)"
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    pass


# ------------------
# Cog + Commands
# ---------------------

class LfgAds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._post_cooldowns: dict[tuple[int,int], float] = {}

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
                # ---- moderation timeout first (origin guild) ----
        try:
            await moderation_db.ensure_user_timeouts_schema()
        except Exception:
            # non-fatal if we can't ensure; we'll still check
            pass
        try:
            if interaction.guild:
                is_timed_out = await moderation_db.is_user_timed_out(interaction.guild.id, interaction.user.id)
                if is_timed_out:
                    until = await moderation_db.get_timeout_until(interaction.guild.id, interaction.user.id)
                    msg = "🚫 You are currently timed out from posting ads."
                    if until:
                        msg += f" You can try again <t:{int(until.timestamp())}:R>."
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                    return
        except Exception:
            # If the timeout lookup fails, we err on the side of allowing, but log later
            pass

        # ---- local cooldown second (only after timeout check) ----
        now_mono = monotonic()
        key = (interaction.guild.id if interaction.guild else 0, interaction.user.id)
        next_ok = self._post_cooldowns.get(key)
        if next_ok and now_mono < next_ok:
            retry = int(next_ok - now_mono)
            msg = f"⏳ Slow down! You can post again in **{retry}s**."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        acked = await safe_ack(interaction, message="Posting your ad…", ephemeral=True, use_thinking=False)
        if not acked:
            return

        async def do_post_work() -> int:
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            try:
                async with pool.acquire() as conn:
                    ad_id = await conn.fetchval(
                        """
                        INSERT INTO lfg_ads (author_id, author_name, game, platform, region, notes, status)
                        VALUES ($1, $2, $3, $4, $5, $6, 'open')
                        RETURNING id
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
                embed.set_footer(
                    text=f"Posted by {interaction.user} • Ad #{ad_id} • Powered by Matchmaker",
                    icon_url="https://i.imgur.com/4x9pIr0.png"
                )

                view = ConnectButton(ad_id=ad_id, timeout=180)

                pool = get_pool()
                posted_count = 0
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT guild_id, lfg_channel_id
                        FROM guild_settings
                        WHERE lfg_channel_id IS NOT NULL
                        """
                    )

                sem = asyncio.Semaphore(MAX_SEND_CONCURRENCY)

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

            except Exception as exc:
                LOGGER.error("Posting to guild channel failed:\n%s", traceback.format_exc())
                raise RuntimeError("POST") from exc

            return posted_count

        try:
            posted = await asyncio.wait_for(do_post_work(), timeout=POST_TIMEOUT_SECONDS)
            if posted <= 0:
                await interaction.edit_original_response(
                    content=(
                        "Your ad couldn’t be posted anywhere yet — no servers have an LFG channel set."
                        "\n• Ask server owners to run `/lfg_channel set #channel`."
                    )
                )
            else:
                await interaction.edit_original_response(
                    content=(
                        "✅ Your ad was posted!"
                        f"\n• **Servers posted to:** {posted}"
                    )
                )
                await db.stats_inc("ads_posted", 1)
                # start cooldown only on successful post
                self._post_cooldowns[key] = monotonic() + USER_COOLDOWN_SEC
        except RuntimeError as exc:
            LOGGER.exception("Post failed")
            msg = "Something went wrong while posting your ad. Please try again."
            if SURFACE_ERROR_CODE:
                msg += f" ({exc})"
            try:
                await interaction.edit_original_response(content=msg)
            except Exception:
                pass
        except (asyncio.TimeoutError, Exception) as exc:
            LOGGER.exception("Post failed")
            msg = "Something went wrong while posting your ad. Please try again."
            if SURFACE_ERROR_CODE:
                msg += " (POST)"
            try:
                await interaction.edit_original_response(content=msg)
            except Exception:
                pass

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            retry = int(error.retry_after)
            msg = f"⏳ Slow down! You can post again in **{retry}s**."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        LOGGER.exception("Unhandled error in LFG ads command", exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(
                "Something went wrong while posting your ad. Please try again.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Something went wrong while posting your ad. Please try again.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
