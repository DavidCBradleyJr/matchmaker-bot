from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands

from ..db import get_pool


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
      True  -> we successfully acknowledged (you may use followups)
      False -> token invalidated or already acked elsewhere (avoid followups)
    """
    try:
        if interaction.response.is_done():
            # Already acked (somewhere else). If we were asked to say something now, try a followup.
            if message:
                try:
                    await interaction.followup.send(message, ephemeral=ephemeral)
                except (discord.NotFound, discord.HTTPException):
                    return False
            return True
        else:
            if message:
                await interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                # "thinking" shows the visible spinner; set to False to ack silently.
                await interaction.response.defer(ephemeral=ephemeral, thinking=use_thinking)
            return True
    except discord.InteractionResponded:
        # Someone else won the race
        return True
    except discord.NotFound:
        # Token invalid/expired/unknown
        return False
    except discord.HTTPException:
        # Something else went wrong — treat as no-ack so we don't chain more errors
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
                # interaction.message is the message that contains the clicked button
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
            # Optional: import logging and log here
            if acked and not sent_followup:
                try:
                    await interaction.followup.send(
                        "Something went wrong while connecting. Try again.",
                        ephemeral=True,
                    )
                    sent_followup = True
                except Exception:
                    # Give up cleanly
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
        Pattern:
        - Ack immediately (safe_ack) to avoid 10062
        - Insert ad
        - Broadcast embed + Connect button to all configured guild channels
        - Follow up to the author (only if ack succeeded)
        """
        # IMPORTANT: don't show the "thinking..." bubble; we only want one final response
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=False)

        pool = get_pool()

        # Create the ad and build the embed
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

            # Fetch all configured LFG channels
            rows = await conn.fetch(
                "SELECT guild_id, lfg_channel_id FROM guild_settings WHERE lfg_channel_id IS NOT NULL"
            )

        view = ConnectButton(ad_id=ad_id)

        posted = 0
        jump_links: list[str] = []

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
                # Collect jump links (limit to a few for the author follow-up)
                if len(jump_links) < 3:
                    jump_links.append(msg.jump_url)
            except discord.Forbidden:
                # Missing perms in that channel — skip
                continue
            except discord.HTTPException:
                # Some other send failure — skip
                continue

        # Tell the author what happened (only if we acked)
        if acked:
            try:
                if posted == 0:
                    await interaction.followup.send(
                        "Your ad was saved, but no servers have an LFG channel configured yet.\n"
                        "Ask server owners to run `/lfg_channel set #channel`.",
                        ephemeral=True,
                    )
                else:
                    # Build a compact list of jump links (up to 3 shown)
                    link_lines = []
                    for i, url in enumerate(jump_links, start=1):
                        link_lines.append(f"{i}. {url}")
                    more = ""
                    if posted > len(jump_links):
                        more = f"\n…and **{posted - len(jump_links)}** more."

                    await interaction.followup.send(
                        "✅ Your ad was posted!"
                        f"\n• **Servers posted to:** {posted}"
                        + (f"\n• **Links:**\n" + "\n".join(link_lines) if link_lines else "")
                        + more,
                        ephemeral=True,
                    )
            except (discord.NotFound, discord.HTTPException):
                # Ack might have been invalidated; nothing else to do
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
