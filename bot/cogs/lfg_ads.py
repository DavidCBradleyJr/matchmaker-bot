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
        ad_id = self.ad_id
        user = interaction.user

        pool = get_pool()
        async with pool.acquire() as conn:
            ad = await conn.fetchrow("SELECT * FROM lfg_ads WHERE id=$1 AND status='active'", ad_id)
            if not ad:
                return await interaction.response.send_message("Sorry, this ad is no longer active.", ephemeral=True)

            if ad["author_id"] == user.id:
                return await interaction.response.send_message("You can’t connect to your own ad.", ephemeral=True)

            # Mark connected
            await conn.execute(
                "UPDATE lfg_ads SET status='connected' WHERE id=$1",
                ad_id
            )

        # DM both parties
        author = interaction.client.get_user(int(ad["author_id"])) or await interaction.client.fetch_user(int(ad["author_id"]))
        ad_owner_dm = (
            f"🎮 **Someone is interested in your LFG ad!**\n"
            f"- Game: **{ad['game']}**\n"
            f"- Platform: {ad['platform'] or 'n/a'}\n"
            f"- Region: {ad['region'] or 'n/a'}\n"
            f"- Notes: {ad['notes'] or '—'}\n\n"
            f"**Interested player:** {user.mention} ({user})"
        )
        clicker_dm = (
            f"🎮 **You connected to an LFG ad!**\n"
            f"- Game: **{ad['game']}**\n"
            f"- Platform: {ad['platform'] or 'n/a'}\n"
            f"- Region: {ad['region'] or 'n/a'}\n"
            f"- Notes: {ad['notes'] or '—'}\n\n"
            f"**Ad owner:** <@{ad['author_id']}>"
        )

        try:
            await author.send(ad_owner_dm)
        except Exception:
            pass
        try:
            await user.send(clicker_dm)
        except Exception:
            pass

        await interaction.response.send_message("✅ I DM’d you both so you can coordinate. Have fun!", ephemeral=True)

class LfgAds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    lfg = app_commands.Group(name="lfg", description="Create and manage LFG ads")

    @lfg.command(name="post", description="Post an LFG ad")
    @app_commands.describe(
        game="The game you want to play",
        platform="PC/PS/Xbox/Switch/Mobile (optional)",
        region="NA/EU/APAC/Global (optional)",
        notes="Anything else people should know (optional)"
    )
    async def post(
        self,
        interaction: discord.Interaction,
        game: str,
        platform: str | None = None,
        region: str | None = None,
        notes: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        pool = get_pool()
        async with pool.acquire() as conn:
            ad_id = await conn.fetchval(
                """
                INSERT INTO lfg_ads (author_id, author_name, game, platform, region, notes)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING id
                """,
                interaction.user.id, str(interaction.user), game, platform, region, notes
            )

            # build embed once
            embed = discord.Embed(
                title=f"LFG: {game}",
                description=notes or "—",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Platform", value=platform or "n/a", inline=True)
            embed.add_field(name="Region", value=region or "n/a", inline=True)
            embed.set_footer(text=f"Posted by {interaction.user} • Ad #{ad_id}")
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

            # find all guilds with an lfg channel configured, and post
            rows = await conn.fetch("SELECT guild_id, lfg_channel_id FROM guild_settings WHERE lfg_channel_id IS NOT NULL")

        view = ConnectButton(ad_id=ad_id)

        posted = 0
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            if not guild:
                continue
            channel = guild.get_channel(int(row["lfg_channel_id"])) if guild else None
            if not channel or not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.send(embed=embed, view=view)
                posted += 1
                # store post record
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO lfg_posts (ad_id, guild_id, channel_id, message_id)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT DO NOTHING
                    """, ad_id, guild.id, channel.id, msg.id)
            except discord.Forbidden:
                # missing perms in that server/channel; skip
                continue
            except Exception:
                continue

        if posted == 0:
            await interaction.followup.send(
                "Your ad was saved, but I don’t see any servers with an LFG channel configured yet.\n"
                "Ask server owners to run `/lfg_channel set #channel`.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Your ad was posted to **{posted}** server(s). I’ll DM you when someone connects.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(LfgAds(bot))
