"""Models for workforce portal source planning and automation runs."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .candidate import Candidate
from .job_description import ParsedJD

AutomationMode = Literal["official_api", "browser", "csv_export", "disabled"]
PortalRunStatus = Literal["not_ready", "running", "completed", "failed"]


class PortalDefinition(BaseModel):
    id: str
    state: str = Field(..., min_length=2, max_length=2)
    state_name: str
    name: str
    employer_url: str
    automation_mode: AutomationMode = "browser"
    credential_env_vars: list[str] = Field(default_factory=list)
    suggested_filters: list[str] = Field(default_factory=list)
    supported_capture_fields: list[str] = Field(default_factory=list)
    search_notes: str
    usage_guidance: str

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.strip().upper()


class SourcePlanRequest(BaseModel):
    jd_text: str
    state: Optional[str] = None
    city: Optional[str] = None
    title_hint: Optional[str] = None

    @field_validator("state")
    @classmethod
    def normalize_optional_state(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else None


class PortalRecommendation(BaseModel):
    portal: PortalDefinition
    search_terms: list[str]
    suggested_filters: list[str]
    automation_ready: bool
    readiness_messages: list[str] = Field(default_factory=list)
    capture_guidance: str


class SourcePlanResponse(BaseModel):
    parsed_jd: ParsedJD
    state: Optional[str]
    city: Optional[str] = None
    recommended_portals: list[PortalRecommendation] = Field(default_factory=list)
    message: Optional[str] = None


class PortalRunRequest(BaseModel):
    jd_text: str
    state: str = Field(..., min_length=2, max_length=2)
    portal_id: str
    city: Optional[str] = None
    limit: int = Field(default=25, ge=1, le=100)
    title_hint: Optional[str] = None

    @field_validator("state")
    @classmethod
    def normalize_run_state(cls, value: str) -> str:
        return value.strip().upper()


class PortalRunCandidate(BaseModel):
    candidate: Candidate
    candidate_id: Optional[str] = None
    saved: bool = False
    skipped_reason: Optional[str] = None


class PortalRunResponse(BaseModel):
    id: Optional[str] = None
    status: PortalRunStatus
    portal: PortalDefinition
    parsed_jd: ParsedJD
    search_terms: list[str]
    candidates: list[PortalRunCandidate] = Field(default_factory=list)
    candidates_found: int = 0
    candidates_saved: int = 0
    candidates_skipped: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
