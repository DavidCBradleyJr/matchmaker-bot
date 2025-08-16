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
    def __init__(self, ad_id: int, timeout: float | None = 600):
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
                SET status = 'connected'
                WHERE id = $1 AND status = 'active'
                RETURNING id, author_id, author_name, game, platform, region, notes
                """,
                self.ad_id,
            )

            if not ad:
                # Already connected/closed or missing
                if acked:
                    try:
                        await interaction.followup.send("Sorry, this ad is no longer active.", ephemeral=True)
                    except (discord.NotFound, discord.HTTPException):
                        pass
                return

            # Don't allow author to connect to themselves
            if int(ad["author_id"]) == user.id:
                # Roll back to active so someone else can click
                await conn.execute(
                    "UPDATE lfg_ads SET status='active' WHERE id=$1 AND status='connected'",
                    self.ad_id,
                )
                if acked:
                    try:
                        await interaction.followup.send("You can’t connect to your own ad.", ephemeral=True)
                    except (discord.NotFound, discord.HTTPException):
                        pass
                return

        # Try to DM both sides; ignore per-user DM failures
        owner_user: discord.User | None = None
        try:
            owner_user = interaction.client.get_user(int(ad["author_id"])) or await interaction.client.fetch_user(
                int(ad["author_id"])
            )
        except Exception:
            owner_user = None

        owner_msg = (
            f"🎮 **Someone is interested in your LFG ad!**\n"
            f"- Game: **{ad['game']}**\n"
            f"- Platform: {ad['platform'] or 'n/a'}\n"
            f"- Region: {ad['region'] or 'n/a'}\n"
            f"- Notes: {ad['notes'] or '—'}\n\n"
            f"**Interested player:** {user.mention} ({user})"
        )
        clicker_msg = (
            f"🎮 **You connected to an LFG ad!**\n"
            f"- Game: **{ad['game']}**\n"
            f"- Platform: {ad['platform'] or 'n/a'}\n"
            f"- Region: {ad['region'] or 'n/a'}\n"
            f"- Notes: {ad['notes'] or '—'}\n\n"
            f"**Ad owner:** <@{ad['author_id']}>"
        )

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
        acked = await safe_ack(interaction, message=None, ephemeral=True, use_thinking=True)

        pool = get_pool()

        # Create the ad and build the embed
        async with pool.acquire() as conn:
            ad_id = await conn.fetchval(
                """
                INSERT INTO lfg_ads (author_id, author_name, game, platform, region, notes)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING id
                """,
                interaction.user.id,
                str(interaction.user),
                game,
                platform,
                region,
                notes,
            )

            embed = discord.Embed(
                title=f"LFG: {game}",
                description=notes or "—",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Platform", value=platform or "n/a", inline=True)
            embed.add_field(name="Region", value=region or "n/a", inline=True)
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
            channel = guild.get_channel(int(row["lfg_channel_id"])) if guild else None
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                msg = await channel.send(embed=embed, view=view)
                posted += 1
                # Persist the post reference
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO lfg_posts (ad_id, guild_id, channel_id, message_id)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT DO NOTHING
                        """,
                        ad_id,
                        guild.id,
                        channel.id,
                        msg.id,
                    )
            except discord.Forbidden:
                # Missing permissions in that channel — skip
                continue
            except Exception:
                # Don’t let one server break the whole broadcast
                continue

        if acked:
            # Only try to follow up if we successfully acknowledged earlier
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
