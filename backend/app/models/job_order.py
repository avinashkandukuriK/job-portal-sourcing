"""Job order + client models — first-class persistent entities."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from .job_description import ComplianceRequirements, ParsedJD


class Client(BaseModel):
    id: Optional[str] = None
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    preferences: dict = Field(default_factory=dict)
    last_order_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClientContact(BaseModel):
    id: Optional[str] = None
    client_id: str
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: bool = False
    last_contacted_at: Optional[datetime] = None


class JobOrder(BaseModel):
    """A persistent open req. Created from a parsed JD; lives until filled/cancelled."""

    id: Optional[str] = None
    client_id: Optional[str] = None
    client_contact_id: Optional[str] = None
    owner_user_id: Optional[str] = None

    title: str
    title_variants: list[str] = Field(default_factory=list)
    raw_jd_text: Optional[str] = None
    parsed_jd: Optional[ParsedJD] = None

    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    required_certs: list[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    min_years_experience: Optional[float] = None
    max_years_experience: Optional[float] = None

    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_miles: Optional[float] = 25
    remote_ok: bool = False

    pay_rate: Optional[float] = None
    bill_rate: Optional[float] = None
    pay_rate_unit: str = "hourly"
    temps_needed: int = 1
    conversion_hours: Optional[int] = None
    shift: Optional[str] = None
    dress_code: Optional[str] = None

    compliance: ComplianceRequirements = Field(default_factory=ComplianceRequirements)

    status: str = "open"  # draft|open|on_hold|filled|cancelled|expired
    fill_deadline: Optional[date] = None
    start_date: Optional[date] = None
    posted_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
