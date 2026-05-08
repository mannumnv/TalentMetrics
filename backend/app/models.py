from __future__ import annotations

from typing import Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy import Date as SqlDate
from sqlalchemy import DateTime as SqlDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class EngineerCategory(Base):
    __tablename__ = "engineer_categories"

    category_id: Mapped[int] = mapped_column(primary_key=True)
    category_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StatusPipeline(Base):
    __tablename__ = "status_pipeline"

    status_id: Mapped[int] = mapped_column(primary_key=True)
    status_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status_order: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Engineer(Base):
    __tablename__ = "engineers"

    engineer_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    ite_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone_number: Mapped[Optional[str]] = mapped_column(String(50))
    total_experience_months: Mapped[int] = mapped_column(Integer, default=0)
    category_id: Mapped[int] = mapped_column(ForeignKey("engineer_categories.category_id"), nullable=False)
    current_status_id: Mapped[int] = mapped_column(ForeignKey("status_pipeline.status_id"), nullable=False)
    date_of_joining: Mapped[Optional[str]] = mapped_column(SqlDate)
    japan_arrival_date: Mapped[Optional[str]] = mapped_column(SqlDate)
    primary_skill: Mapped[Optional[str]] = mapped_column(String(150))
    secondary_skills: Mapped[Optional[dict]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category = relationship("EngineerCategory")
    current_status = relationship("StatusPipeline")


class EngineerMonthlyPresence(Base):
    __tablename__ = "engineer_monthly_presence"

    presence_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    ite_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    source_sheet: Mapped[Optional[str]] = mapped_column(String(255))
    source_row: Mapped[Optional[int]] = mapped_column(Integer)
    was_present: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("ite_number", "source_month"),)


class EngineerMonthlyRecord(Base):
    __tablename__ = "engineer_monthly_records"

    record_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    staff_no: Mapped[Optional[str]] = mapped_column("スタッフNO", String(50))
    ite_number: Mapped[str] = mapped_column("ITE番号", String(50), nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column("名前", String(200))
    honorific: Mapped[Optional[str]] = mapped_column("呼称", String(100))
    date_of_joining: Mapped[Optional[str]] = mapped_column("入社日", SqlDate)
    office: Mapped[Optional[str]] = mapped_column("オフィス", String(150))
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    upload_timestamp: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (UniqueConstraint("ITE番号", "month", "year"),)


class EngineerStatusHistory(Base):
    __tablename__ = "engineer_status_history"

    status_history_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("engineers.engineer_id"), nullable=False, index=True)
    from_status_id: Mapped[Optional[int]] = mapped_column(ForeignKey("status_pipeline.status_id"))
    to_status_id: Mapped[int] = mapped_column(ForeignKey("status_pipeline.status_id"), nullable=False)
    effective_from: Mapped[str] = mapped_column(SqlDate, nullable=False)
    effective_to: Mapped[Optional[str]] = mapped_column(SqlDate)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    changed_by: Mapped[Optional[str]] = mapped_column(String(150))
    changed_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("effective_to IS NULL OR effective_to >= effective_from"),)


class Contract(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("engineers.engineer_id"), nullable=False, index=True)
    contract_number: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    contract_start_date: Mapped[str] = mapped_column(SqlDate, nullable=False)
    contract_end_date: Mapped[str] = mapped_column(SqlDate, nullable=False)
    contract_status: Mapped[str] = mapped_column(String(50), default="Active")
    signed_date: Mapped[Optional[str]] = mapped_column(SqlDate)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (CheckConstraint("contract_end_date >= contract_start_date"),)


class ContractExtension(Base):
    __tablename__ = "contract_extensions"

    extension_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False, index=True)
    previous_end_date: Mapped[str] = mapped_column(SqlDate, nullable=False)
    new_end_date: Mapped[str] = mapped_column(SqlDate, nullable=False)
    extension_reason: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(String(150))
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("new_end_date > previous_end_date"),
        UniqueConstraint("contract_id", "previous_end_date", "new_end_date"),
    )


class MonthlySnapshot(Base):
    __tablename__ = "engineer_monthly_snapshots"

    snapshot_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    snapshot_month: Mapped[str] = mapped_column(SqlDate, nullable=False, index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("engineers.engineer_id"), nullable=False)
    ite_number: Mapped[str] = mapped_column(String(50), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("engineer_categories.category_id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("status_pipeline.status_id"), nullable=False)
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.contract_id"))
    contract_start_date: Mapped[Optional[str]] = mapped_column(SqlDate)
    contract_end_date: Mapped[Optional[str]] = mapped_column(SqlDate)
    contract_status: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("snapshot_month", "engineer_id"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_log_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_pk: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    old_data: Mapped[Optional[dict]] = mapped_column(JSON)
    new_data: Mapped[Optional[dict]] = mapped_column(JSON)
    changed_by: Mapped[Optional[str]] = mapped_column(String(150))
    changed_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), index=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(100))


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    validation_run_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    run_name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_file_name: Mapped[Optional[str]] = mapped_column(String(255))
    started_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[str]] = mapped_column(SqlDateTime(timezone=True))
    run_status: Mapped[str] = mapped_column(String(50), default="Running")
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    valid_records: Mapped[int] = mapped_column(Integer, default=0)
    error_records: Mapped[int] = mapped_column(Integer, default=0)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(150))


class ValidationLog(Base):
    __tablename__ = "validation_logs"

    validation_log_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    validation_run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.validation_run_id"), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    ite_number: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    field_name: Mapped[Optional[str]] = mapped_column(String(100))
    invalid_value: Mapped[Optional[str]] = mapped_column(Text)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    row_number: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())


class EngineerSourceState(Base):
    __tablename__ = "engineer_source_state"

    ite_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())


class AppUser(Base):
    __tablename__ = "app_users"

    user_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    dob: Mapped[str] = mapped_column(SqlDate, nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    session_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.user_id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user = relationship("AppUser")


class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"

    activity_log_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("app_users.user_id"), index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    role: Mapped[Optional[str]] = mapped_column(String(30))
    login_time: Mapped[Optional[str]] = mapped_column(SqlDateTime(timezone=True))
    action_performed: Mapped[str] = mapped_column(String(150), nullable=False)
    timestamp: Mapped[str] = mapped_column(SqlDateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("AppUser")
