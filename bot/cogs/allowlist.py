import discord
from discord import app_commands
from discord.ext import commands
from .. import config
from ..db import get_allowed_guilds, add_allowed_guilds, remove_allowed_guilds

class Allowlist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="allowlist_add", description="Add guild IDs to the staging allowlist")
    async def allowlist_add(self, itx: discord.Interaction, guild_ids: str):
        if config.ENVIRONMENT != "staging":
            return await itx.response.send_message("This command is staging-only.", ephemeral=True)
        ids = {int(x) for x in guild_ids.replace(" ", "").split(",") if x}
        added = await add_allowed_guilds("staging", ids)
        await itx.response.send_message(f"Added/updated {added} guild(s).", ephemeral=True)

    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="allowlist_remove", description="Remove guild IDs from the staging allowlist")
    async def allowlist_remove(self, itx: discord.Interaction, guild_ids: str):
        if config.ENVIRONMENT != "staging":
            return await itx.response.send_message("This command is staging-only.", ephemeral=True)
        ids = {int(x) for x in guild_ids.replace(" ", "").split(",") if x}
        removed = await remove_allowed_guilds("staging", ids)
        await itx.response.send_message(f"Removed {removed} guild(s).", ephemeral=True)

    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="allowlist_list", description="Show the current staging allowlist")
    async def allowlist_list(self, itx: discord.Interaction):
        if config.ENVIRONMENT != "staging":
            return await itx.response.send_message("This command is staging-only.", ephemeral=True)
        ids = await get_allowed_guilds("staging")
        text = ", ".join(str(i) for i in sorted(ids)) or "— (empty) —"
        await itx.response.send_message(f"Staging allowlist:\n`{text}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Allowlist(bot))
