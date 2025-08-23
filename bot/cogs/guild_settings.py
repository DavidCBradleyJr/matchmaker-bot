import discord
from discord import app_commands
from discord.ext import commands
from ..db import get_pool  # keep this import style consistent with your repo

class GuildSettings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory cache: { guild_id: lfg_channel_id }
        if not hasattr(bot, "lfg_channels"):
            bot.lfg_channels: dict[int, int] = {}

    group = app_commands.Group(name="lfg_channel", description="Configure the LFG ads channel")

    @commands.Cog.listener()
    async def on_ready(self):
        """On every (re)connect/deploy, re-hydrate the LFG channel cache from the DB."""
        try:
            async with get_pool().acquire() as conn:
                rows = await conn.fetch("SELECT guild_id, lfg_channel_id FROM guild_settings")
            self.bot.lfg_channels = {
                int(r["guild_id"]): int(r["lfg_channel_id"])
                for r in rows
                if r["lfg_channel_id"]
            }
        except Exception:
            # Don't explode startup if DB is temporarily unavailable; just log.
            # Your logger may be different; adjust as needed.
            import logging
            logging.getLogger(__name__).exception("Failed to hydrate lfg_channels from DB on_ready")

    async def get_lfg_channel_id(self, guild_id: int) -> int | None:
        """Get LFG channel ID for a guild, with DB fallback and cache refresh."""
        cid = self.bot.lfg_channels.get(guild_id)
        if cid:
            return cid

        try:
            async with get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT lfg_channel_id FROM guild_settings WHERE guild_id=$1",
                    guild_id
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("DB error reading lfg_channel_id")
            return None

        if row and row["lfg_channel_id"]:
            cid = int(row["lfg_channel_id"])
            self.bot.lfg_channels[guild_id] = cid
            return cid
        return None

    async def resolve_lfg_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """
        Return the TextChannel for the guild's LFG setting.
        Uses cache, then fetches from DB, and finally uses API fetch if cache misses.
        """
        cid = await self.get_lfg_channel_id(guild.id)
        if not cid:
            return None

        ch = guild.get_channel(cid)
        if ch is None:
            try:
                ch = await guild.fetch_channel(cid)  # API fallback if not cached
            except Exception:
                ch = None
        return ch

    @group.command(name="set", description="Set the channel where LFG ads should be broadcast")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            async with get_pool().acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, lfg_channel_id)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET lfg_channel_id = EXCLUDED.lfg_channel_id, updated_at = NOW()
                    """,
                    interaction.guild.id, channel.id
                )
            # Update the in-memory cache immediately
            self.bot.lfg_channels[interaction.guild.id] = channel.id

            await interaction.response.send_message(
                f"✅ LFG ads will be posted in {channel.mention}.",
                ephemeral=True
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to set LFG channel")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Something went wrong while saving the LFG channel. Please try again.",
                    ephemeral=True
                )

    @group.command(name="show", description="Show the current LFG ads channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def show_channel(self, interaction: discord.Interaction):
        # Prefer cache, fall back to DB if necessary
        ch = await self.resolve_lfg_channel(interaction.guild)
        if ch:
            msg = f"📣 Current LFG channel: {ch.mention}"
        else:
            # If we *do* have an ID but the channel is missing (deleted?), show raw ID
            cid = await self.get_lfg_channel_id(interaction.guild.id)
            if cid:
                msg = f"📣 Current LFG channel (not cached): <#{cid}>"
            else:
                msg = "ℹ️ No LFG channel set yet. Use `/lfg_channel set #channel`."
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildSettings(bot))
