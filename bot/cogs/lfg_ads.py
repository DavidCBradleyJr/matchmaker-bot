import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


# ---------------------------
# Utilities / permissions
# ---------------------------

def is_guild_admin_or_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user == interaction.guild.owner:
            return True
        perms = interaction.user.guild_permissions
        return perms.manage_guild or perms.administrator
    return app_commands.check(predicate)


# ---------------------------
# Fancy DM helper
# ---------------------------

async def send_pretty_interest_dm(
    recipient: discord.User | discord.Member,
    poster: discord.User | discord.Member,
    game: str,
    notes: Optional[str],
    ad_message: discord.Message,
    guild: discord.Guild,
    channel: discord.abc.GuildChannel
):
    """Compose and send a polished DM to the interested user."""
    color_seed = (sum(ord(c) for c in (game or "")) % 255)
    color = discord.Color.from_rgb(80, 120 + color_seed // 2, 255 - color_seed)

    embed = discord.Embed(
        title="You’re connected! 🎮",
        description=(
            f"You clicked **I’m interested** on an LFG post.\n\n"
            f"**Poster:** {poster.mention}\n"
            f"**Server:** **{guild.name}**\n"
            f"**Channel:** <#{channel.id}>"
        ),
        color=color,
        timestamp=datetime.datetime.utcnow()
    )

    try:
        poster_avatar = poster.display_avatar.url
    except Exception:
        poster_avatar = None

    embed.set_author(name=str(poster), icon_url=poster_avatar or discord.Embed.Empty)
    embed.set_thumbnail(url=poster_avatar or discord.Embed.Empty)

    embed.add_field(name="Game", value=f"`{game}`", inline=True)

    if notes:
        trimmed = notes if len(notes) <= 256 else notes[:253] + "…"
        embed.add_field(name="Notes", value=trimmed, inline=False)

    embed.set_footer(text="Tip: Send a friendly opener and set expectations (roles, region, mic, time).")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Open the original ad", url=ad_message.jump_url, emoji="🔗"))

    opener = (
        f"Hey {poster.display_name}! Saw your LFG for {game}. "
        f"I’m down to play. Region: ___ | Role: ___ | Mic: Yes/No | Available: ___"
    )

    await recipient.send(embed=embed, view=view)
    await recipient.send("Quick opener you can copy/paste:\n" f"> {opener}")


# ---------------------------
# UI: Connect Button & View
# ---------------------------

class ConnectButton(discord.ui.Button):
    """'I'm interested' button. Sends a DM to the clicker with details and a jump link."""

    def __init__(
        self,
        poster: discord.User | discord.Member,
        game: str,
        notes: Optional[str],
        message: discord.Message,
    ):
        super().__init__(label="I’m interested", style=discord.ButtonStyle.primary, emoji="🤝")
        self.poster = poster
        self.game = game
        self.notes = notes
        self.message = message  # the posted ad message (for jump_url)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return await interaction.response.send_message(
                "This button must be used in a server.", ephemeral=True
            )

        # Optional safety: prevent the poster from clicking their own ad.
        if interaction.user.id == getattr(self.poster, "id", None):
            return await interaction.response.send_message(
                "You can’t connect to your own ad.", ephemeral=True
            )

        # Try the pretty DM
        try:
            await send_pretty_interest_dm(
                recipient=interaction.user,
                poster=self.poster,
                game=self.game,
                notes=self.notes,
                ad_message=self.message,
                guild=interaction.guild,
                channel=self.message.channel,
            )
            await interaction.response.send_message(
                "✅ Check your DMs — I sent you a clean summary and a quick opener.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I couldn’t DM you (DMs might be closed). Open your DMs and click again.",
                ephemeral=True
            )
        except Exception:
            logger.exception("Failed to DM interested user", extra={
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "poster_id": getattr(self.poster, 'id', None),
                "message_id": getattr(self.message, 'id', None),
            })
            await interaction.response.send_message(
                "Something went wrong while connecting you. Please try again.",
                ephemeral=True
            )


class LFGView(discord.ui.View):
    """Holds the Connect button and any future controls."""

    def __init__(
        self,
        poster: discord.User | discord.Member,
        game: str,
        notes: Optional[str],
        message: Optional[discord.Message] = None,
        timeout: Optional[float] = 600.0,
    ):
        super().__init__(timeout=timeout)
        # Button needs the posted message to build a jump_url. We’ll attach it after send().
        self.poster = poster
        self.game = game
        self.notes = notes
        self.message = message
        # Button instance (message will be injected post-send)
        self.connect_button = ConnectButton(
            poster=poster, game=game, notes=notes, message=message or discord.Message
        )
        self.add_item(self.connect_button)

    def attach_message(self, message: discord.Message):
        """Call this right after sending the ad to wire jump_url etc."""
        self.message = message
        # update button’s reference too
        self.connect_button.message = message


# ---------------------------
# Cog: /lfg commands
# ---------------------------

class LFGAds(commands.Cog):
    """Slash commands to set LFG channel and post ads."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    lfg = app_commands.Group(name="lfg", description="Configure and use LFG features")

    @lfg.command(name="setchannel", description="Set the channel where LFG ads will be posted (admin/owner only).")
    @is_guild_admin_or_owner()
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # NOTE: Persist this to your existing config/DB solution.
        # Here we stash it in guild data via bot.tree (replace with your DB call).
        try:
            # Replace this with your own: await db.save_lfg_channel(interaction.guild_id, channel.id)
            self.bot._lfg_channel_map = getattr(self.bot, "_lfg_channel_map", {})
            self.bot._lfg_channel_map[interaction.guild_id] = channel.id
            await interaction.response.send_message(
                f"✅ LFG channel set to {channel.mention}.", ephemeral=True
            )
        except Exception:
            logger.exception("Failed setting LFG channel", extra={"guild_id": interaction.guild_id, "channel_id": channel.id})
            await interaction.response.send_message(
                "Something went wrong while saving the channel. Please try again.",
                ephemeral=True
            )

    @lfg.command(name="post", description="Post an LFG ad to the configured channel.")
    async def post(self, interaction: discord.Interaction, game: str, notes: Optional[str] = None):
        # Fetch configured channel (swap this out for your DB fetch)
        lfg_channel_id = getattr(self.bot, "_lfg_channel_map", {}).get(interaction.guild_id)
        if not lfg_channel_id:
            return await interaction.response.send_message(
                "No LFG channel has been set yet. Ask an admin to run `/lfg setchannel #channel`.",
                ephemeral=True
            )

        channel = interaction.guild.get_channel(lfg_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Configured LFG channel is invalid. Ask an admin to set it again.",
                ephemeral=True
            )

        # Compose the ad embed
        color_seed = (sum(ord(c) for c in (game or "")) % 255)
        color = discord.Color.from_rgb(255 - color_seed, 120 + color_seed // 2, 80)

        ad = discord.Embed(
            title=f"LFG: {game}",
            description=(notes[:1024] if notes else "No notes provided."),
            color=color,
            timestamp=datetime.datetime.utcnow()
        )
        ad.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        ad.set_footer(text="Click the button below if you’re interested!")

        # Prepare the view (message gets attached post-send for jump_url)
        view = LFGView(poster=interaction.user, game=game, notes=notes, message=None)

        try:
            posted = await channel.send(embed=ad, view=view)
            view.attach_message(posted)

            await interaction.response.send_message(
                f"✅ Your LFG ad for **{game}** was posted in {channel.mention}.",
                ephemeral=True
            )
        except Exception:
            logger.exception("Failed to post LFG ad", extra={
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "channel_id": channel.id if channel else None,
                "game": game,
            })
            await interaction.response.send_message(
                "Something went wrong while posting your ad. Please try again.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LFGAds(bot))
