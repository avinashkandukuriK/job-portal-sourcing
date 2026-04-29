"""Output of a sourcing run."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .candidate import Candidate
from .job_description import ParsedJD


class ScoredCandidate(BaseModel):
    candidate: Candidate
    score: float = Field(..., ge=0, le=100)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    reasoning: str = ""  # short human-readable explanation


class AdapterRunStats(BaseModel):
    source: str
    enabled: bool
    candidates_found: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class SearchResult(BaseModel):
    id: Optional[str] = None  # set after persistence
    parsed_jd: ParsedJD
    candidates: list[ScoredCandidate] = Field(default_factory=list)
    adapter_stats: list[AdapterRunStats] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
