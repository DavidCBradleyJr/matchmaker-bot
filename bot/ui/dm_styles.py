from __future__ import annotations

import datetime
from typing import Optional

import discord


async def send_pretty_interest_dm(
    recipient: discord.User | discord.Member,
    poster: discord.User | discord.Member,
    ad_id: int,
    game: str,
    platform: Optional[str],
    region: Optional[str],
    notes: Optional[str],
    message_jump: Optional[str],
    guild: Optional[discord.Guild],
) -> None:
    color_seed = (sum(ord(c) for c in (game or "")) % 255)
    color = discord.Color.from_rgb(80, 120 + color_seed // 2, 255 - color_seed)

    lines = [
        "You clicked **I’m interested** on an LFG post.",
        "",
        f"**Poster:** {poster.mention}",
        f"**Server:** {guild.name if guild else 'Unknown'}",
        "",
        f"**Game:** `{game}`",
    ]
    if platform:
        lines.append(f"**Platform:** `{platform}`")
    if region:
        lines.append(f"**Region:** `{region}`")
    if notes:
        lines.extend(["", f"**Notes:** {notes}"])

    # Optional site link
    lines.append("\n[🔗 matchmaker-site.fly.dev](https://matchmaker-site.fly.dev/)")

    embed = discord.Embed(
        title="You’re connected! 🎮",
        description="\n".join(lines),
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )

    avatar = getattr(getattr(poster, "display_avatar", None), "url", None)
    if avatar:
        embed.set_author(name=str(poster), icon_url=avatar)
        embed.set_thumbnail(url=avatar)

    embed.set_footer(
        text=f"Ad #{ad_id} • Powered by Matchmaker",
        icon_url="https://i.imgur.com/4x9pIr0.png"
    )

    view = discord.ui.View()
    if message_jump:
        view.add_item(discord.ui.Button(label="Open the ad", url=message_jump, emoji="🔗"))

    view.add_item(
        discord.ui.Button(
            label="Message poster",
            url=f"discord://-/users/{poster.id}",
            emoji="✉️"
        )
    )

    opener = (
        f"Hey {poster.display_name}! Saw your LFG for {game}. "
        "I’m down to play. Region: ___ | Role: ___ | Mic: Yes/No | Available: ___"
    )

    await recipient.send(embed=embed, view=view)
    await recipient.send("Quick opener you can copy/paste:\n" f"> {opener}")
