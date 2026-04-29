"""Job description models — raw JD input + structured ParsedJD."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    """Raw JD as pasted by recruiter."""

    text: str
    title_hint: Optional[str] = None


class ComplianceRequirements(BaseModel):
    """Compliance requirements parsed from a JD."""

    requires_i9: bool = True
    requires_everify: bool = True
    requires_drug_test: bool = False
    drug_test_panel: Optional[int] = None
    requires_background_check: bool = False
    background_check_levels: list[str] = Field(default_factory=list)
    requires_nda: bool = False
    requires_schedule_c: bool = False
    requires_ehs_training: bool = False


class ParsedJD(BaseModel):
    """Structured query extracted from a JD. The orchestrator passes this
    to every adapter and to the scorer.
    """

    title: str
    title_variants: list[str] = Field(default_factory=list)

    # Skills + certs
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    required_certs: list[str] = Field(default_factory=list)

    # Experience
    min_years_experience: Optional[float] = None
    max_years_experience: Optional[float] = None
    seniority: Optional[str] = None

    # Commercial
    pay_rate: Optional[float] = None
    pay_rate_unit: Optional[str] = None
    bill_rate: Optional[float] = None
    conversion_hours: Optional[int] = None
    temps_needed: int = 1
    shift: Optional[str] = None

    # Location
    location: Optional[str] = None
    location_country: str = "US"
    state: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    radius_miles: Optional[float] = 25
    remote_ok: bool = False

    # Compliance
    compliance: ComplianceRequirements = Field(default_factory=ComplianceRequirements)

    # Free-text extras
    keywords: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """POST /api/search payload from the React frontend."""

    jd_text: str
    job_order_id: Optional[str] = None
    sources: Optional[list[str]] = None
    mode: str = "internal_external"  # 'internal' | 'external' | 'internal_external'
    limit_per_source: int = 25
    title_hint: Optional[str] = None
    include_premium: bool = False
