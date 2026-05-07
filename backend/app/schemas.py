from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


StatusName = Literal["Training", "In Japan (Bench)", "Assigned (Pre-Join)", "Joined", "Historical"]


class EngineerCreate(BaseModel):
    ite_number: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    total_experience_months: int = 0
    current_status: StatusName = "Training"
    date_of_joining: Optional[date] = None
    japan_arrival_date: Optional[date] = None
    primary_skill: Optional[str] = None
    secondary_skills: List[str] = []

class EngineerResponse(BaseModel):
    engineer_id: int
    ite_number: str
    full_name: str
    email: Optional[str]
    category: str
    current_status: str
    total_experience_months: int
    date_of_joining: Optional[date] = None


class StatusUpdateRequest(BaseModel):
    to_status: StatusName
    effective_from: date
    reason: Optional[str] = None


class StatusUpdateResponse(BaseModel):
    ite_number: str
    from_status: str
    to_status: str
    effective_from: date


class PipelineSummaryItem(BaseModel):
    status: str
    key: str
    count: int
    percentage: float


class UploadResponse(BaseModel):
    validation_run_id: int
    total_records: int
    inserted_records: int
    updated_records: int
    unchanged_records: int
    error_records: int


class AuditLogResponse(BaseModel):
    audit_log_id: int
    table_name: str
    record_pk: str
    action: str
    old_data: Optional[dict]
    new_data: Optional[dict]
    changed_by: Optional[str]
    changed_at: datetime
    source_system: Optional[str]

