from __future__ import annotations
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

class GuildWindowLimiter:
    """
    In-memory sliding-window limiter per (guild_id, channel_id).
    Limits to at most `max_events` within `window_sec`.
    """
    def __init__(self, window_sec: int, max_events: int) -> None:
        self.window_sec = window_sec
        self.max_events = max_events
        self._hits: Dict[Tuple[int, int], Deque[float]] = defaultdict(deque)

    def allow(self, guild_id: int, channel_id: int) -> bool:
        now = time.time()
        key = (guild_id, channel_id)
        q = self._hits[key]
        cutoff = now - self.window_sec
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True

    def remaining(self, guild_id: int, channel_id: int) -> int:
        key = (guild_id, channel_id)
        return max(self.max_events - len(self._hits[key]), 0)
