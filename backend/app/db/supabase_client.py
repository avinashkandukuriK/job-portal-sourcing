"""Supabase client singleton — uses service-role key for backend writes."""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_supabase():
    """Returns a Supabase client. Returns None if not configured (dev mode)."""
    settings = get_settings()
    if not settings.has_supabase:
        logger.warning("Supabase not configured — DB operations will be no-ops")
        return None
    try:
        from supabase import create_client
        # Prefer service-role key for backend writes; fall back to anon
        key = getattr(settings, "supabase_service_key", None) or settings.supabase_key
        client = create_client(settings.supabase_url, key)
        logger.info("Supabase client initialized")
        return client
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to init Supabase client: %s", exc)
        return None


def has_supabase() -> bool:
    return get_supabase() is not None
