# bot/main.py
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

INTENTS = discord.Intents.none()  # slash-commands only for MVP
SYNC_GUILDS = []  # put test guild IDs here for faster command sync (optional)

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            application_id=None,  # discord.py infers from token
        )

    async def setup_hook(self):
        # Load cogs/extensions
        await self.load_extension("bot.cogs.lfg")

        # Sync application commands
        if SYNC_GUILDS:
            # Faster dev sync to a specific guild
            for gid in SYNC_GUILDS:
                await self.tree.sync(guild=discord.Object(id=gid))
        else:
            # Global sync (takes a minute the very first time)
            await self.tree.sync()

async def start_health_server():
    app = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
    await site.start()
    logging.getLogger("health").info("health server started on /health")

async def main():
    token = config.DISCORD_TOKEN
    if not token or len(token) < 50:
        raise RuntimeError("DISCORD_TOKEN is missing or malformed.")

    bot = Bot()
    # run bot and health server together
    await asyncio.gather(
        start_health_server(),
        bot.start(token),
    )

if __name__ == "__main__":
    asyncio.run(main())
