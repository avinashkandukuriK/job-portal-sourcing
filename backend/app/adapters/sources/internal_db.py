"""Internal candidate database adapter.

The first thing every search hits — your warm pool. Returns candidates from
your Supabase that match the parsed JD, scored against the JD's structured
fields. This is the highest-leverage source for staffing agencies because
60-80% of fills come from past candidates.
"""
from __future__ import annotations

import logging

from app.adapters import (
    AdapterAccessMode,
    AdapterCapability,
    AdapterMetadata,
    AdapterTier,
    RoleType,
    SourceAdapter,
    register_adapter,
)
from app.models import Candidate, ParsedJD

logger = logging.getLogger(__name__)


@register_adapter
class InternalDBAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="internal_db",
        display_name="Internal Candidate Database",
        version="1.0.0",
        description="Search your own Supabase pool of past applicants and placed temps.",
        tier=AdapterTier.INTERNAL,
        access_mode=AdapterAccessMode.LOCAL_DB,
        capabilities=[
            AdapterCapability.SEARCH,
            AdapterCapability.ENRICH,
            AdapterCapability.BULK,
        ],
        supported_role_types=[
            RoleType.BLUE_COLLAR,
            RoleType.HOURLY_GENERAL,
            RoleType.SKILLED_TRADE,
            RoleType.DRIVING,
            RoleType.HEALTHCARE,
            RoleType.HOSPITALITY,
            RoleType.OFFICE,
            RoleType.GENERAL,
        ],
        supported_regions=["US"],
        required_env_vars=["SUPABASE_URL", "SUPABASE_KEY"],
    )

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        # Concrete query implemented in Task #10 (Supabase persistence layer).
        # Sketch: WHERE skills ?| array[required_skills] AND country = jd.country
        #        AND (location ILIKE %loc% OR loc within radius)
        #        ORDER BY last_contacted DESC LIMIT n
        from app.db.repository import search_candidates  # type: ignore
        return await search_candidates(jd, limit=limit)
