# bot/cogs/lfg_ads.py
from __future__ import annotations

import asyncio
import logging
import os
import traceback

import discord
from discord import app_commands, ui
from discord.ext import commands

from ..db import get_pool

# ---------------------
# Logging
# ---------------------

LOGGER = logging.getLogger("lfg_ads")
if not LOGGER.handlers:
    # Basic handler if none configured globally
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s lfg_ads: %(message)s")
    h.setFormatter(fmt)
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

# ---------------------
# Config
# ---------------------

# Overall time we allow for inserting + broadcasting the ad before showing a timeout to the user.
POST_TIMEOUT_SECONDS = int(os.getenv("LFG_POST_TIMEOUT_SECONDS", "60"))

# Max concurrent channel sends to avoid rate-limit spikes
MAX_SEND_CONCURRENCY = int(os.getenv("LFG_POST_MAX_CONCURRENCY", "5"))

# Per-channel send timeout (seconds)
PER_SEND_TIMEOUT = int(os.getenv("LFG_POST_PER_SEND_TIMEOUT", "8"))

# If set (e.g. "1"), include a short exception typename in the ephemeral error to help debugging
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
    """
    Safely acknowledge an interaction exactly once.
    Returns:
      True  -> we successfully acknowledged (you may use followups / edits)
      False -> token invalidated or already acked elsewhere (avoid followups/edits)
    """
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
                # Visible immediate message (better UX during deploys than a spinner)
                await interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                # "thinking" shows the visible spinner; keep False when you don't want a bubble
                await interaction.response.defer(ephemeral=ephemeral, thinking=use_thinking)
            return True
    except discord.InteractionResponded:
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        return False


def _err_code(prefix: str, exc: BaseException | None = None) -> str:
    """Short error identifier to surface to the user (optional)."""
    if not SURFACE_ERROR_CODE:
        return ""
    typ = type(exc).__name__ if exc else ""
    return f" ({prefix}:{typ})" if typ else f" ({prefix})"


# ---------------------
# Button View
# ---------------------

class ConnectButton(ui.View):
    def __init__(self, ad_id: int, *, timeout: float | None = 1800):
        super().__init__(timeout=timeout)
        self.ad_id = ad_id

    @ui.button(label="I’m interested", style=discord.ButtonStyle.success, custom_id="lfg:connect")
    async def connect(self, interaction: discord.Interaction, button: ui.Button):
        # ACK early, but silently (no spinner bubble)
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=False)

        sent_followup = False
        try:
            user = interaction.user
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

            # Atomically switch ad to connected; first click wins.
            async with pool.acquire() as conn:
                ad = await conn.fetchrow(
                    """
                    UPDATE lfg_ads
                    SET status = 'connected', connector_id = $1, connector_name = $2
                    WHERE id = $3 AND status = 'open'
                    RETURNING id, author_id, author_name, game, platform, region, notes
                    """,
                    int(user.id),
                    str(user),
                    self.ad_id,
                )

            if not ad:
                if acked:
                    await interaction.followup.send(
                        "Someone already connected with this ad. Try another one!",
                        ephemeral=True,
                    )
                    sent_followup = True
                return

            # DM both parties (best-effort; failures are swallowed)
            owner_id = int(ad["author_id"])
            owner_user = interaction.client.get_user(owner_id) or await interaction.client.fetch_user(owner_id)

            if owner_user:
                try:
                    await owner_user.send(
                        f"✅ Someone is interested in your **{ad['game']}** ad (#{self.ad_id}).\n"
                        f"Connector: {user.mention}"
                    )
                except Exception:
                    LOGGER.info("Owner DM failed; continuing", exc_info=True)

            try:
                await user.send(
                    f"✅ I connected you with **{ad['author_name']}** for **{ad['game']}**.\n"
                    f"Start a chat here: <@{owner_id}>"
                )
            except Exception:
                LOGGER.info("Connector DM failed; continuing", exc_info=True)

            # Include a jump link back to the exact message the user clicked
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


# ---------------------
# Cog + Commands
# ---------------------

class LfgAds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    lfg = app_commands.Group(name="lfg_ad", description="Create and manage LFG ads")

    @lfg.command(name="post", description="Post an LFG ad")
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

        async def do_post_work() -> tuple[int, list[tuple[str, str]]]:
            """Insert the ad, broadcast it, and return (posted_count, [(server_name, jump_url), ...])."""
            # --- DB INSERT + SETTINGS FETCH ---
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
            jump_links: list[tuple[str, str]] = []  # (server_name, jump_url)
            posted_count = 0

            async def send_one(guild_id: int, channel_id: int) -> tuple[bool, tuple[str, str] | None]:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return False, None
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.TextChannel):
                    return False, None
                async with sem:
                    try:
                        msg = await asyncio.wait_for(channel.send(embed=embed, view=view), timeout=PER_SEND_TIMEOUT)
                        return True, (guild.name, msg.jump_url)
                    except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError) as exc:
                        LOGGER.info("Send to %s#%s failed: %r", guild.name, channel_id, exc)
                        return False, None

            tasks = [
                asyncio.create_task(send_one(int(r["guild_id"]), int(r["lfg_channel_id"])))
                for r in rows
            ]

            for coro in asyncio.as_completed(tasks):
                ok, info = await coro
                if ok:
                    posted_count += 1
                    if info and len(jump_links) < 3:
                        jump_links.append(info)

            return posted_count, jump_links

        try:
            posted, jump_links = await asyncio.wait_for(do_post_work(), timeout=POST_TIMEOUT_SECONDS)
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
                link_lines = [f"{i}. **{server}** — {url}" for i, (server, url) in enumerate(jump_links, start=1)]
                more = f"\n…and **{posted - len(jump_links)}** more." if posted > len(jump_links) else ""
                await interaction.edit_original_response(
                    content=(
                        "✅ Your ad was posted!"
                        f"\n• **Servers posted to:** {posted}"
                        + (f"\n• **Links:**\n" + "\n".join(link_lines) if link_lines else "")
                        + more
                    )
                )
        except (discord.NotFound, discord.HTTPException):
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
