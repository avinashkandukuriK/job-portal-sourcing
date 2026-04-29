"""Pipeline + submission + placement models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

PIPELINE_STAGES = [
    "new", "contacted", "screened", "submitted", "interview",
    "offer", "placed", "started", "converted", "rejected", "withdrawn",
]


class PipelineEntry(BaseModel):
    id: Optional[str] = None
    job_order_id: str
    candidate_id: str
    owner_user_id: Optional[str] = None
    stage: str = "new"
    score: Optional[float] = None
    rank: Optional[int] = None
    stage_changed_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    interview_at: Optional[datetime] = None
    offered_at: Optional[datetime] = None
    placed_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Submission(BaseModel):
    id: Optional[str] = None
    pipeline_entry_id: Optional[str] = None
    job_order_id: str
    candidate_id: str
    submitted_by_user_id: Optional[str] = None
    sent_to_email: Optional[str] = None
    package_document_id: Optional[str] = None
    notes: Optional[str] = None
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    client_feedback: Optional[str] = None
    client_feedback_at: Optional[datetime] = None
    decision: Optional[str] = None  # interview|reject|hold|hire
    decision_at: Optional[datetime] = None


class Placement(BaseModel):
    id: Optional[str] = None
    candidate_id: str
    job_order_id: str
    owner_user_id: Optional[str] = None

    status: str = "submitted"
    pay_rate: Optional[float] = None
    bill_rate: Optional[float] = None
    margin_pct: Optional[float] = None

    submitted_at: Optional[datetime] = None
    interview_at: Optional[datetime] = None
    offered_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    conversion_eligible_at: Optional[date] = None
    converted_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    termination_reason: Optional[str] = None

    nda_signed_at: Optional[datetime] = None
    schedule_c_signed_at: Optional[datetime] = None
    ehs_completed_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ComplianceStatus(BaseModel):
    id: Optional[str] = None
    candidate_id: str
    placement_id: Optional[str] = None

    i9_status: str = "pending"
    i9_completed_at: Optional[datetime] = None

    everify_status: str = "pending"
    everify_run_at: Optional[datetime] = None
    everify_case_number: Optional[str] = None

    drug_test_status: str = "pending"
    drug_test_panel: Optional[int] = None
    drug_test_completed_at: Optional[datetime] = None

    background_check_status: str = "pending"
    background_check_completed_at: Optional[datetime] = None

    nda_signed_at: Optional[datetime] = None
    schedule_c_signed_at: Optional[datetime] = None
    ehs_training_completed_at: Optional[datetime] = None

    notes: Optional[str] = None
    next_review_due_at: Optional[datetime] = None
