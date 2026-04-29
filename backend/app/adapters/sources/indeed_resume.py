"""Indeed Resume (PAID) adapter — STUB.

Indeed's Resume Search API requires an authenticated Employer subscription
(~$150-250/month per recruiter seat). Drop in your INDEED_PUBLISHER_ID +
auth token in .env to enable.

This file is a working stub: registered, queryable from the UI source picker
(appears in the Premium tab with cost shown), but `search()` raises
`AdapterDisabled` until configured. Implement real API calls once you have
credentials.
"""
from __future__ import annotations

import logging

from app.adapters import (
    AdapterAccessMode,
    AdapterCapability,
    AdapterCost,
    AdapterDisabled,
    AdapterMetadata,
    AdapterTier,
    RoleType,
    SourceAdapter,
    register_adapter,
)
from app.config import get_settings
from app.models import Candidate, ParsedJD

logger = logging.getLogger(__name__)


@register_adapter
class IndeedResumeAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="indeed_resume",
        display_name="Indeed Resume (Paid)",
        version="0.1.0",
        description="Indeed's resume database — gold-standard US blue-collar coverage. Requires Indeed Employer subscription.",
        homepage="https://employers.indeed.com/",
        tier=AdapterTier.PREMIUM,
        access_mode=AdapterAccessMode.PAID_API,
        capabilities=[
            AdapterCapability.SEARCH,
            AdapterCapability.EMAIL_LOOKUP,
            AdapterCapability.PHONE_LOOKUP,
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
        cost=AdapterCost(
            per_search=0.0,
            per_candidate=0.0,
            currency="USD",
            notes="Subscription model (~$150-250/mo/seat); per-action cost amortized.",
        ),
        rate_limit_per_min=30,
        required_env_vars=["INDEED_PUBLISHER_ID"],
        is_experimental=True,
    )

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        settings = get_settings()
        if not settings.indeed_publisher_id:
            raise AdapterDisabled(
                "Set INDEED_PUBLISHER_ID + auth token in .env. "
                "See https://employers.indeed.com/api"
            )

        # TODO: real implementation
        # 1. POST to Indeed Resume Search API with parsed JD
        # 2. Parse response into Candidate model
        # 3. Map skills, certs, location, contact to our schema
        logger.warning("IndeedResumeAdapter.search() not yet implemented")
        return []
