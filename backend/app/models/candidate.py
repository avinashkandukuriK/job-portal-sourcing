"""Normalized candidate schema. Every adapter must map its source payload to this."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None
    personal_url: Optional[str] = None


class ExperienceItem(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None  # ISO or "2021-03"
    end_date: Optional[str] = None
    description: Optional[str] = None


class EducationItem(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


class Candidate(BaseModel):
    """The unified candidate record — every adapter normalizes into this."""

    # Identification
    source: str = Field(..., description="Adapter name, e.g. 'github', 'wellfound'")
    source_id: str = Field(..., description="Native ID from the source")
    profile_url: Optional[str] = None

    # Profile
    name: str
    headline: Optional[str] = None  # one-line title/bio
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None  # ISO-2 (e.g. "US")

    # Skills / experience
    skills: list[str] = Field(default_factory=list)
    years_experience: Optional[float] = None
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)

    # Contact
    contact: ContactInfo = Field(default_factory=ContactInfo)

    # Source-specific extras (kept verbatim for debugging / future use)
    raw: dict = Field(default_factory=dict)

    # Metadata
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def dedupe_key(self) -> str:
        """Used by the orchestrator to merge duplicates across sources."""
        if self.contact.linkedin_url:
            return f"linkedin:{self.contact.linkedin_url.lower()}"
        if self.contact.github_url:
            return f"github:{self.contact.github_url.lower()}"
        if self.contact.email:
            return f"email:{self.contact.email.lower()}"
        return f"{self.source}:{self.source_id}"
