from __future__ import annotations

import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


JWT_SECRET = os.environ.get("JWT_SECRET", "").strip() or "dev-only-change-me"
ACCESS_MINUTES = max(5, _int("ACCESS_MINUTES", 15))
REFRESH_DAYS = max(1, _int("REFRESH_DAYS", 30))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/sync.db")).expanduser()
TRUST_PROXY = os.environ.get("TRUST_PROXY", "").strip() in {"1", "true", "yes"}
AUTH_RATE_PER_MIN = max(3, _int("AUTH_RATE_PER_MIN", 20))
SYNC_RATE_PER_MIN = max(10, _int("SYNC_RATE_PER_MIN", 60))
PASSWORD_MIN = 8
PASSWORD_MAX = 128
