from __future__ import annotations

import logging
import os
import traceback
from typing import Set

import discord
from discord.ext import commands

from .. import config
from ..db import get_allowed_guilds, add_allowed_guilds, remove_allowed_guilds

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    h = logging.StreamHandler()
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # set this to YOUR Discord user ID


def is_owner():
    async def predicate(ctx: commands.Context) -> bool:
        return OWNER_ID != 0 and int(ctx.author.id) == OWNER_ID
    return commands.check(predicate)


def _parse_ids(arg: str) -> Set[int]:
    # supports "123,456  , 789"
    return {int(x) for x in arg.replace(" ", "").split(",") if x}


class Allowlist(commands.Cog):
    """
    Owner-only allowlist management (prefix commands, hidden from slash picker).
    Staging-only per your config.ENVIRONMENT.
    Usage:
      !al add 123,456,789
      !al remove 123,456
      !al list
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dm_owner(self, ctx: commands.Context, content: str):
        try:
            await ctx.author.send(content)
        except Exception:
            LOGGER.info("Failed to DM owner allowlist result", exc_info=True)

    async def _delete_invocation(self, ctx: commands.Context):
        try:
            if ctx.guild and ctx.message and ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.message.delete()
        except Exception:
            pass

    @commands.group(name="al", invoke_without_command=True, hidden=True)
    @is_owner()
    async def al_group(self, ctx: commands.Context):
        if config.ENVIRONMENT != "staging":
            await self._dm_owner(ctx, "This command is staging‑only.")
            await self._delete_invocation(ctx)
            return
        await self._dm_owner(ctx,
            "Allowlist controls:\n"
            "• `!al add 123,456,789`\n"
            "• `!al remove 123,456`\n"
            "• `!al list`"
        )
        await self._delete_invocation(ctx)

    @al_group.command(name="add", hidden=True)
    @is_owner()
    async def al_add(self, ctx: commands.Context, guild_ids: str):
        if config.ENVIRONMENT != "staging":
            await self._dm_owner(ctx, "This command is staging‑only.")
            await self._delete_invocation(ctx)
            return
        try:
            ids = _parse_ids(guild_ids)
            added = await add_allowed_guilds("staging", ids)
            await self._dm_owner(ctx, f"✅ Added/updated **{added}** guild(s) to the staging allowlist.")
        except Exception:
            LOGGER.error("allowlist add failed:\n%s", traceback.format_exc())
            await self._dm_owner(ctx, "Something went wrong while updating the allowlist. Please try again.")
        finally:
            await self._delete_invocation(ctx)

    @al_group.command(name="remove", hidden=True)
    @is_owner()
    async def al_remove(self, ctx: commands.Context, guild_ids: str):
        if config.ENVIRONMENT != "staging":
            await self._dm_owner(ctx, "This command is staging‑only.")
            await self._delete_invocation(ctx)
            return
        try:
            ids = _parse_ids(guild_ids)
            removed = await remove_allowed_guilds("staging", ids)
            await self._dm_owner(ctx, f"🗑️ Removed **{removed}** guild(s) from the staging allowlist.")
        except Exception:
            LOGGER.error("allowlist remove failed:\n%s", traceback.format_exc())
            await self._dm_owner(ctx, "Something went wrong while updating the allowlist. Please try again.")
        finally:
            await self._delete_invocation(ctx)

    @al_group.command(name="list", hidden=True)
    @is_owner()
    async def al_list(self, ctx: commands.Context):
        if config.ENVIRONMENT != "staging":
            await self._dm_owner(ctx, "This command is staging‑only.")
            await self._delete_invocation(ctx)
            return
        try:
            ids = await get_allowed_guilds("staging")
            text = ", ".join(str(i) for i in sorted(ids)) or "— (empty) —"
            await self._dm_owner(ctx, f"Staging allowlist:\n`{text}`")
        except Exception:
            LOGGER.error("allowlist list failed:\n%s", traceback.format_exc())
            await self._dm_owner(ctx, "Something went wrong while reading the allowlist. Please try again.")
        finally:
            await self._delete_invocation(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Allowlist(bot))
