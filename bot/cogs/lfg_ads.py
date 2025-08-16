# bot/cogs/lfg_ads.py
import discord
from discord import app_commands, ui
from discord.ext import commands
from ..db import get_pool


class ConnectButton(ui.View):
    def __init__(self, ad_id: int, timeout: float | None = 600):
        super().__init__(timeout=timeout)
        self.ad_id = ad_id

    @ui.button(label="I’m interested", style=discord.ButtonStyle.success, custom_id="lfg:connect")
    async def connect(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        user = interaction.user
        ad_row = None

        pool = get_pool()
        async with pool.acquire() as conn:
            ad_row = await conn.fetchrow(
                """
                UPDATE lfg_ads
                SET status='connected'
                WHERE id=$1 AND status='active'
                RETURNING id, author_id, author_name, game, platform, region, notes
                """,
                self.ad_id,
            )

            if not ad_row:
                # Either nonexistent or already connected/closed
                await interaction.followup.send(
                    "Sorry, this ad is no longer active.", ephemeral=True
                )
                return

            # Prevent ad owner from "connecting" to themselves
            if int(ad_row["author_id"]) == user.id:
                # Roll back the status change for this edge case (set it back to active)
                await conn.execute(
                    "UPDATE lfg_ads SET status='active' WHERE id=$1 AND status='connected'",
                    self.ad_id,
                )
                await interaction.followup.send(
                    "You can’t connect to your own ad.", ephemeral=True
                )
                return

        # 2) DM both parties (non-blocking per user; swallow individual DM failures)
        # Build messages once
        ad_owner_dm = (
            f"🎮 **Someone is interested in your LFG ad!**\n"
            f"- Game: **{ad_row['game']}**\n"
            f"- Platform: {ad_row['platform'] or 'n/a'}\n"
            f"- Region: {ad_row['region'] or 'n/a'}\n"
            f"- Notes: {ad_row['notes'] or '—'}\n\n"
            f"**Interested player:** {user.mention} ({user})"
        )
        clicker_dm = (
            f"🎮 **You connected to an LFG ad!**\n"
            f"- Game: **{ad_row['game']}**\n"
            f"- Platform: {ad_row['platform'] or 'n/a'}\n"
            f"- Region: {ad_row['region'] or 'n/a'}\n"
            f"- Notes: {ad_row['notes'] or '—'}\n\n"
            f"**Ad owner:** <@{ad_row['author_id']}>"
        )

        try:
            author_user = interaction.client.get_user(int(ad_row["author_id"])) or await interaction.client.fetch_user(
                int(ad_row["author_id"])
            )
        except Exception:
            author_user = None

        # Try to DM ad owner
        if author_user:
            try:
                await author_user.send(ad_owner_dm)
            except Exception:
                pass

        # Try to DM clicker
        try:
            await user.send(clicker_dm)
        except Exception:
            pass

        # 3) Ephemeral confirmation back to clicker
        await interaction.followup.send(
            "✅ I DM’d you both so you can coordinate. Have fun!",
            ephemeral=True,
        )


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
        Posts an LFG ad to every guild that has an LFG channel configured.
        Pattern:
        - Write ad to DB
        - Broadcast embed + Connect button
        """
        # 1) ACK immediately
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        pool = get_pool()
        async with pool.acquire() as conn:
            # Create the ad record
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
            embed.set_footer(text=f"Posted by {interaction.user} • Ad #{ad_id}")
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

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
                # Store the post record
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
                # Missing perms in that server/channel; skip
                continue
            except Exception:
                continue

        if posted == 0:
            await interaction.followup.send(
                "Your ad was saved, but I don’t see any servers with an LFG channel configured yet.\n"
                "Ask server owners to run `/lfg_channel set #channel`.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"✅ Your ad was posted to **{posted}** server(s). I’ll DM you when someone connects.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot), override=True)
