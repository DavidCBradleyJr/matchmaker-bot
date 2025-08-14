import asyncio
import logging
import os

import discord
from discord.ext import commands
from aiohttp import web

from . import config
from .health import make_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

INTENTS = discord.Intents.none()
SYNC_GUILDS = []

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            application_id=None,
        )

    async def setup_hook(self):
        await self.load_extension("bot.cogs.lfg")
        if SYNC_GUILDS:
            tree = self.tree
            await tree.sync(guild=discord.Object(id=SYNC_GUILDS[0]))
        else:
            await self.tree.sync()

async def start_health_server():
    app = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
    await site.start()

async def main():
    bot = Bot()
    # run bot and health server together
    await asyncio.gather(
        start_health_server(),
        bot.start(config.DISCORD_TOKEN),
    )

if __name__ == "__main__":
    asyncio.run(main())
