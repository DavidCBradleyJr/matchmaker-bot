from __future__ import annotations

import datetime
from typing import Optional

import discord


async def send_pretty_interest_dm(
    recipient: discord.User | discord.Member,
    poster: discord.User | discord.Member,
    ad_id: int,
    game: str,
    notes: Optional[str],
    message_jump: Optional[str],
    guild: Optional[discord.Guild],
) -> None:
    """
    Compose and send a polished DM to the connector after they click "I'm interested".
    """
    # Nice, stable-but-varied accent color based on game name
    color_seed = (sum(ord(c) for c in (game or "")) % 255)
    color = discord.Color.from_rgb(80, 120 + color_seed // 2, 255 - color_seed)

    embed = discord.Embed(
        title="You’re connected! 🎮",
        description=(
            "You clicked **I’m interested** on an LFG post.\n\n"
            f"**Poster:** {poster.mention}\n"
            f"**Server:** {guild.name if guild else 'Unknown'}"
            "\n\n[🔗 Powered by Matchmaker](https://matchmaker-site.fly.dev/)"
        ),
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )

    # Avatar (safe access)
    avatar = getattr(getattr(poster, "display_avatar", None), "url", None)
    if avatar:
        embed.set_author(name=str(poster), icon_url=avatar)
        embed.set_thumbnail(url=avatar)

    embed.add_field(name="Game", value=f"`{game}`", inline=True)

    if notes:
        trimmed = notes if len(notes) <= 256 else notes[:253] + "…"
        embed.add_field(name="Notes", value=trimmed, inline=False)

    embed.set_footer(text=f"Ad #{ad_id} • Powered by Matchmaker", icon_url="https://i.imgur.com/4x9pIr0.png")

    # DM view with a jump back to the original ad
    view = discord.ui.View()
    if message_jump:
        view.add_item(discord.ui.Button(label="Open the ad", url=message_jump, emoji="🔗"))

    # Provide a quick, copy/paste opener in a follow-up message
    opener = (
        f"Hey {poster.display_name}! Saw your LFG for {game}. "
        "I’m down to play. Region: ___ | Role: ___ | Mic: Yes/No | Available: ___"
    )

    await recipient.send(embed=embed, view=view)
    await recipient.send("Quick opener you can copy/paste:\n" f"> {opener}")
