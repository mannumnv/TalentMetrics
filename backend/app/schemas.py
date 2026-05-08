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


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    dob: date
    location: str = Field(min_length=1)
    role: Literal["admin", "user"] = "user"


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str


class UserResponse(BaseModel):
    user_id: int
    email: str
    role: str
    dob: date
    location: str


class AdminUserResponse(BaseModel):
    user_id: int
    email: str
    role: str
    dob: date
    location: str
    created_at: datetime


class DobUpdateRequest(BaseModel):
    dob: date


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class UserActivityLogResponse(BaseModel):
    activity_log_id: int
    user_email: Optional[str]
    role: Optional[str]
    login_time: Optional[datetime]
    action_performed: str
    timestamp: datetime
