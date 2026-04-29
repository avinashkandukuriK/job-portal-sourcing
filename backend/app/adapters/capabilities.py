"""Adapter metadata + capability model.

Every adapter declares an `AdapterMetadata` block. The orchestrator, search-mode
picker UI, and reporting layers read this — never the adapter code itself —
so adding a new adapter is a self-contained drop-in.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AdapterTier(str, Enum):
    """High-level cost bucket — drives the Premium / Non-Premium UI tabs."""

    INTERNAL = "internal"          # Your own DB
    NON_PREMIUM = "non_premium"    # Free / low-cost public sources
    PREMIUM = "premium"            # Paid APIs / databases
    INBOUND = "inbound"            # Receives applications, doesn't search


class AdapterAccessMode(str, Enum):
    """How the adapter retrieves data."""

    PUBLIC_API = "public_api"          # Free public REST/GraphQL API
    PAID_API = "paid_api"              # Authenticated paid API
    SCRAPING = "scraping"              # HTML scraping (Playwright/HTTP)
    BROWSER_AUTOMATION = "browser"     # Logged-in browser automation
    GOOGLE_X_RAY = "google_x_ray"      # SerpAPI/Google search over public pages
    INBOUND_FORM = "inbound_form"      # Candidates apply to us
    INBOUND_FEED = "inbound_feed"      # Webhook/RSS/email
    LOCAL_DB = "local_db"              # Internal Supabase


class RoleType(str, Enum):
    """Coarse role taxonomy — adapters declare what they're useful for so the
    orchestrator can skip irrelevant sources (e.g. don't hit GitHub for a
    forklift role).
    """

    BLUE_COLLAR = "blue_collar"        # Forklift, warehouse, manual labor
    HOURLY_GENERAL = "hourly_general"  # Retail, food service, gig
    SKILLED_TRADE = "skilled_trade"    # Electrician, plumber, welder, HVAC
    DRIVING = "driving"                # CDL, delivery, rideshare
    HEALTHCARE = "healthcare"          # CNA, MA, RN, home health
    HOSPITALITY = "hospitality"        # Hotel, restaurant
    OFFICE = "office"                  # Admin, customer service
    PROFESSIONAL = "professional"      # White-collar, knowledge work
    TECH = "tech"                      # Engineering, data, design
    GENERAL = "general"                # Spans many


class AdapterCapability(str, Enum):
    """Granular feature flags — UI/orchestrator branches on these."""

    SEARCH = "search"                  # Can search candidates by query
    ENRICH = "enrich"                  # Can enrich a known candidate
    POST_JOB = "post_job"              # Can post an outbound job listing
    EMAIL_LOOKUP = "email_lookup"      # Returns candidate email
    PHONE_LOOKUP = "phone_lookup"      # Returns candidate phone
    VERIFY = "verify"                  # Can verify validity (phone/email/cert)
    BULK = "bulk"                      # Supports bulk operations
    STREAM = "stream"                  # Streams results vs single-shot batch


class AdapterStatus(str, Enum):
    """Runtime state."""

    READY = "ready"
    DISABLED_NO_CONFIG = "disabled_no_config"
    DISABLED_USER = "disabled_user"
    DEGRADED = "degraded"
    DOWN = "down"
    EXPERIMENTAL = "experimental"


class AdapterCost(BaseModel):
    """Cost model used by the Premium-tier UI to estimate spend per search."""

    per_search: float = 0.0
    per_candidate: float = 0.0
    per_enrich: float = 0.0
    currency: str = "USD"
    notes: Optional[str] = None


class AdapterMetadata(BaseModel):
    """The single source of truth about what an adapter is and what it does.

    The orchestrator reads this; never inspects the adapter class itself.
    """

    # Identity
    name: str = Field(..., description="Stable ID, lowercase snake_case, e.g. 'craigslist'")
    display_name: str = Field(..., description="Human label for UI")
    version: str = "1.0.0"
    description: str = ""
    homepage: Optional[str] = None
    maintainer: Optional[str] = None  # who owns this adapter

    # Classification
    tier: AdapterTier
    access_mode: AdapterAccessMode
    capabilities: list[AdapterCapability] = Field(default_factory=lambda: [AdapterCapability.SEARCH])

    # Coverage
    supported_role_types: list[RoleType] = Field(default_factory=list)
    supported_regions: list[str] = Field(default_factory=lambda: ["US"])  # ISO-2 codes or "GLOBAL"
    supported_metros: list[str] = Field(default_factory=list)  # optional finer granularity

    # Cost / rate-limit
    cost: AdapterCost = Field(default_factory=AdapterCost)
    rate_limit_per_min: Optional[int] = None
    rate_limit_per_day: Optional[int] = None

    # Config requirements (read by the registry to flag adapters as enabled/disabled)
    required_env_vars: list[str] = Field(default_factory=list)
    optional_env_vars: list[str] = Field(default_factory=list)

    # Compliance / risk flags (UI can warn the recruiter)
    tos_risk: bool = False                # Scraping that violates ToS
    requires_consent: bool = False        # User must accept terms before enabling
    pii_returned: bool = True             # Returns personal info (most do)

    # Observability
    is_experimental: bool = False
    deprecated: bool = False
    deprecation_message: Optional[str] = None
