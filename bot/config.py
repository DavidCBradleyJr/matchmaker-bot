import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
PUBLIC_INVITE_URL = os.getenv("PUBLIC_INVITE_URL", "")

def _parse_ids(raw: str) -> set[int]:
    ids = set()
    for part in (raw or "").replace(" ", "").split(","):
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                pass
    return ids

# Fallback if DB not configured
STAGING_ALLOWED_GUILDS: set[int] = _parse_ids(os.getenv("STAGING_ALLOWED_GUILDS", ""))

DATABASE_URL = os.getenv("DATABASE_URL", "")
STAGING_STATUS = "🧪 Staging Bot"
PROD_STATUS = "✅ Matchmaker Bot"