from __future__ import annotations

import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands

from ..db import get_pool


# ---------------------
# Config
# ---------------------

# How long we're willing to wait for posting the ad and broadcasting to channels
POST_TIMEOUT_SECONDS = 15


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
                    pass

            try:
                await user.send(
                    f"✅ I connected you with **{ad['author_name']}** for **{ad['game']}**.\n"
                    f"Start a chat here: <@{owner_id}>"
                )
            except Exception:
                pass

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

        except Exception:
            if acked and not sent_followup:
                try:
                    await interaction.followup.send(
                        "Something went wrong while connecting. Try again.",
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
        - Within a timeout, insert ad + broadcast to configured guild channels
        - Edit the original message to the final result (success or guidance)
        """
        # Send the initial message (so deploy interrupts don't leave a spinner)
        acked = await safe_ack(interaction, message="Posting your ad…", ephemeral=True, use_thinking=False)

        if not acked:
            # If we couldn't ack, there's nothing safe to edit later
            return

        async def do_post_work() -> tuple[int, list[tuple[str, str]]]:
            """Insert the ad, broadcast it, and return (posted_count, [(server_name, jump_url), ...])."""
            pool = get_pool()

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

                rows = await conn.fetch(
                    "SELECT guild_id, lfg_channel_id FROM guild_settings WHERE lfg_channel_id IS NOT NULL"
                )

            view = ConnectButton(ad_id=ad_id)

            posted = 0
            jump_links: list[tuple[str, str]] = []  # (server_name, jump_url)

            for row in rows:
                guild = self.bot.get_guild(int(row["guild_id"]))
                if not guild:
                    continue

                channel = guild.get_channel(int(row["lfg_channel_id"]))
                if not isinstance(channel, discord.TextChannel):
                    continue

                try:
                    msg = await channel.send(embed=embed, view=view)
                    posted += 1
                    if len(jump_links) < 3:
                        jump_links.append((guild.name, msg.jump_url))
                except discord.Forbidden:
                    continue
                except discord.HTTPException:
                    continue

            return posted, jump_links

        try:
            posted, jump_links = await asyncio.wait_for(
                do_post_work(),
                timeout=POST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            try:
                await interaction.edit_original_response(
                    content=(
                        "⏳ Timed out while posting your ad. Please try again."
                    )
                )
            except Exception:
                pass
            return
        except Exception:
            # Generic fallback
            try:
                await interaction.edit_original_response(
                    content="Something went wrong while posting your ad. Please try again."
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
