# bot/cogs/status.py
import time, discord
from discord import app_commands
from discord.ext import commands

START = time.time()

class Status(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="status", description="Bot health & latency")
    async def status(self, itx: discord.Interaction):
        uptime = int(time.time() - START)
        await itx.response.send_message(
            f"✅ Online | ping: {round(self.bot.latency*1000)}ms | uptime: {uptime}s",
            ephemeral=True
        )

async def setup(bot): await bot.add_cog(Status(bot))
