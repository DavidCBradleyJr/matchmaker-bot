import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..database.privacy_db import delete_user_data  # cogs -> database (..)

logger = logging.getLogger(__name__)

def _confirm_embed() -> discord.Embed:
    return discord.Embed(
        title="Delete your data?",
        description=(
            "This will erase data the bot has stored **about you**, such as:\n"
            "• LFG ads you posted and your ad clicks\n"
            "• Reports you filed and reports about you\n"
            "• Bot timeouts and post cooldowns targeting you\n\n"
            "**This cannot be undone.**"
        ),
        color=discord.Color.red(),
    )

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, on_confirm, *, timeout: Optional[float] = 60.0):
        super().__init__(timeout=timeout)
        self.on_confirm = on_confirm
        self.value: Optional[bool] = None
        self.message: Optional[discord.Message] = None

    def _is_requester(self, interaction: discord.Interaction) -> bool:
        try:
            return interaction.user.id == self.message.interaction.user.id  # type: ignore[union-attr]
        except Exception:
            return False

    @discord.ui.button(label="Confirm delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._is_requester(interaction):
            await interaction.response.send_message(
                "Only the original requester can confirm this.", ephemeral=True
            )
            return
        self.value = True
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.on_confirm(interaction)
            await interaction.followup.send(
                "✅ Your data has been deleted (where applicable).", ephemeral=True
            )
        except Exception:
            logger.exception("Delete data failed for user_id=%s", interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while deleting your data. Please try again.",
                ephemeral=True,
            )
        finally:
            self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._is_requester(interaction):
            await interaction.response.send_message(
                "Only the original requester can cancel this.", ephemeral=True
            )
            return
        self.value = False
        await interaction.response.send_message("Cancelled. No data was deleted.", ephemeral=True)
        self.stop()

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

class Privacy(commands.Cog):
    """Privacy & data management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="delete_data",
        description="Delete all data this bot has stored about you."
    )
    async def delete_data(self, interaction: discord.Interaction):
        async def _do_delete(ix: discord.Interaction):
            await delete_user_data(ix.user.id)

        view = ConfirmDeleteView(on_confirm=_do_delete)
        await interaction.response.send_message(embed=_confirm_embed(), view=view, ephemeral=True)
        try:
            sent = await interaction.original_response()
            view.message = sent
        except Exception:
            logger.exception("Failed to fetch original response for delete_data view.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Privacy(bot))
