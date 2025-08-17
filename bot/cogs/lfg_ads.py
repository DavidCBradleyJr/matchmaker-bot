# bot/cogs/lfg_ads.py
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
    Returns True if we successfully acknowledged (so it's safe to use followups later),
    False if the token was already invalid/acknowledged (so avoid followups).
    """
    try:
        if interaction.response.is_done():
            # Already acked elsewhere — try a followup only if we have a message right now.
            if message:
                try:
                    await interaction.followup.send(message, ephemeral=ephemeral)
                except (discord.NotFound, discord.HTTPException):
                    return False
            return True
        else:
            if message:
                # Instant ack with a visible ephemeral message
                await interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                # Thinking bar (defer)
                await interaction.response.defer(ephemeral=ephemeral, thinking=use_thinking)
            return True
    except discord.InteractionResponded:
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
        # ACK early, defensively
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=True)

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
                try:
                    await interaction.followup.send(
                        "Someone already connected with this ad. Try another one!", ephemeral=True
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass
            return

        # DM both parties
        owner_id = int(ad["author_id"])
        owner_msg = (
            f"✅ Someone is interested in your **{ad['game']}** ad (#{self.ad_id}).\n"
            f"Connector: {user.mention}"
        )
        clicker_msg = (
            f"✅ I connected you with **{ad['author_name']}** for **{ad['game']}**.\n"
            f"Start a chat here: <@{owner_id}>"
        )

        # Try to fetch owner and DM
        owner_user = interaction.client.get_user(owner_id) or await interaction.client.fetch_user(owner_id)
        if owner_user:
            try:
                await owner_user.send(owner_msg)
            except Exception:
                pass

        try:
            await user.send(clicker_msg)
        except Exception:
            pass

        if acked:
            try:
                await interaction.followup.send("✅ I DM’d you both so you can coordinate. Have fun!", ephemeral=True)
            except (discord.NotFound, discord.HTTPException):
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

            title_bits = [game]
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
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            if not guild:
                continue

            channel = guild.get_channel(int(row["lfg_channel_id"]))
            if not channel or not isinstance(channel, discord.TextChannel):
                continue

            try:
                await channel.send(embed=embed, view=view)
                posted += 1
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
                    await interaction.followup.send(
                        f"✅ Your ad was posted to **{posted}** server(s). I’ll DM you when someone connects.",
                        ephemeral=True,
                    )
            except (discord.NotFound, discord.HTTPException):
                # Ack might have been invalidated; nothing else to do
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
