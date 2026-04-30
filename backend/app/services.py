from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models


STATUS_ORDER = [
    "Training",
    "In Japan (Bench)",
    "Assigned (Pre-Join)",
    "Joined",
    "Historical",
]

ALLOWED_TRANSITIONS = {
    "Training": {"In Japan (Bench)", "Historical"},
    "In Japan (Bench)": {"Assigned (Pre-Join)", "Historical"},
    "Assigned (Pre-Join)": {"Joined", "In Japan (Bench)", "Historical"},
    "Joined": {"In Japan (Bench)", "Historical"},
    "Historical": set(),
}


def seed_reference_data(db: Session) -> None:
    for name in ["Fresher", "Experienced"]:
        if not db.scalar(select(models.EngineerCategory).where(models.EngineerCategory.category_name == name)):
            db.add(models.EngineerCategory(category_name=name))

    for index, name in enumerate(STATUS_ORDER, start=1):
        if not db.scalar(select(models.StatusPipeline).where(models.StatusPipeline.status_name == name)):
            db.add(models.StatusPipeline(status_name=name, status_order=index, is_terminal=name == "Historical"))
    db.commit()


def categorize_engineer(total_experience_months: int) -> str:
    return "Experienced" if total_experience_months >= 24 else "Fresher"


def get_category(db: Session, name: str) -> models.EngineerCategory:
    category = db.scalar(select(models.EngineerCategory).where(models.EngineerCategory.category_name == name))
    if not category:
        raise ValueError(f"Unknown category: {name}")
    return category


def get_status(db: Session, name: str) -> models.StatusPipeline:
    status = db.scalar(select(models.StatusPipeline).where(models.StatusPipeline.status_name == name))
    if not status:
        raise ValueError(f"Unknown status: {name}")
    return status


def audit_log(db: Session, table_name: str, record_pk: str, action: str, old_data: Optional[dict], new_data: Optional[dict], changed_by: str, source_system: str) -> None:
    db.add(models.AuditLog(
        table_name=table_name,
        record_pk=record_pk,
        action=action,
        old_data=old_data,
        new_data=new_data,
        changed_by=changed_by,
        source_system=source_system,
    ))


def create_engineer(db: Session, payload: Any, changed_by: str = "API") -> models.Engineer:
    category = get_category(db, categorize_engineer(payload.total_experience_months))
    status = get_status(db, payload.current_status)
    engineer = models.Engineer(
        ite_number=payload.ite_number,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
        total_experience_months=payload.total_experience_months,
        category_id=category.category_id,
        current_status_id=status.status_id,
        date_of_joining=payload.date_of_joining,
        japan_arrival_date=payload.japan_arrival_date,
        primary_skill=payload.primary_skill,
        secondary_skills=payload.secondary_skills,
    )
    db.add(engineer)
    db.flush()
    db.add(models.EngineerStatusHistory(
        engineer_id=engineer.engineer_id,
        to_status_id=status.status_id,
        effective_from=payload.date_of_joining or date.today(),
        reason="Initial status",
        changed_by=changed_by,
    ))
    audit_log(db, "engineers", str(engineer.engineer_id), "INSERT", None, {"ite_number": engineer.ite_number}, changed_by, "HR_ANALYTICS_API")
    return engineer


def validate_transition(from_status: str, to_status: str) -> None:
    if from_status == to_status:
        return
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"Invalid status transition: {from_status} -> {to_status}")


def update_engineer_status(db: Session, engineer: models.Engineer, to_status_name: str, effective_from: date, reason: Optional[str], changed_by: str = "API") -> None:
    from_status_name = engineer.current_status.status_name
    validate_transition(from_status_name, to_status_name)
    if from_status_name == to_status_name:
        return

    to_status = get_status(db, to_status_name)
    active_history = db.scalar(
        select(models.EngineerStatusHistory)
        .where(models.EngineerStatusHistory.engineer_id == engineer.engineer_id)
        .where(models.EngineerStatusHistory.effective_to.is_(None))
    )
    if active_history:
        active_history.effective_to = effective_from - timedelta(days=1)

    db.add(models.EngineerStatusHistory(
        engineer_id=engineer.engineer_id,
        from_status_id=engineer.current_status_id,
        to_status_id=to_status.status_id,
        effective_from=effective_from,
        reason=reason,
        changed_by=changed_by,
    ))
    engineer.current_status_id = to_status.status_id
    engineer.updated_at = datetime.utcnow()
    audit_log(
        db,
        "engineers",
        str(engineer.engineer_id),
        "STATUS_CHANGE",
        {"current_status": from_status_name},
        {"current_status": to_status_name},
        changed_by,
        "HR_ANALYTICS_API",
    )


def source_hash(row: Dict[str, Any]) -> str:
    parts = [str(row.get(key) or "").strip() for key in sorted(row.keys())]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def add_validation_error(db: Session, run_id: int, row_number: Optional[int], ite_number: Optional[str], field: str, rule_code: str, message: str, invalid_value: Any = None) -> None:
    db.add(models.ValidationLog(
        validation_run_id=run_id,
        severity="ERROR",
        entity_type="Engineer",
        ite_number=ite_number,
        field_name=field,
        invalid_value=None if invalid_value is None else str(invalid_value),
        rule_code=rule_code,
        message=message,
        row_number=row_number,
    ))


def generate_monthly_snapshot(db: Session, snapshot_month: date) -> int:
    inserted = 0
    engineers = db.scalars(select(models.Engineer).where(models.Engineer.is_active.is_(True))).all()
    for engineer in engineers:
        existing = db.scalar(
            select(models.MonthlySnapshot)
            .where(models.MonthlySnapshot.snapshot_month == snapshot_month)
            .where(models.MonthlySnapshot.engineer_id == engineer.engineer_id)
        )
        contract = db.scalar(
            select(models.Contract)
            .where(models.Contract.engineer_id == engineer.engineer_id)
            .where(models.Contract.contract_status.in_(["Active", "Extended"]))
            .order_by(models.Contract.contract_end_date.desc())
        )
        if not existing:
            existing = models.MonthlySnapshot(snapshot_month=snapshot_month, engineer_id=engineer.engineer_id, ite_number=engineer.ite_number)
            db.add(existing)
            inserted += 1
        existing.category_id = engineer.category_id
        existing.status_id = engineer.current_status_id
        existing.contract_id = contract.contract_id if contract else None
        existing.contract_start_date = contract.contract_start_date if contract else None
        existing.contract_end_date = contract.contract_end_date if contract else None
        existing.contract_status = contract.contract_status if contract else None
    audit_log(db, "engineer_monthly_snapshots", snapshot_month.isoformat(), "SNAPSHOT_GENERATION", None, {"count": len(engineers)}, "SYSTEM_BATCH", "DAILY_ENGINEER_SYNC")
    return inserted


def pipeline_summary(db: Session) -> List[Dict[str, Any]]:
    total = db.scalar(select(func.count(models.Engineer.engineer_id))) or 0
    rows = db.execute(
        select(models.StatusPipeline.status_name, func.count(models.Engineer.engineer_id))
        .join(models.Engineer, models.Engineer.current_status_id == models.StatusPipeline.status_id, isouter=True)
        .group_by(models.StatusPipeline.status_name, models.StatusPipeline.status_order)
        .order_by(models.StatusPipeline.status_order)
    ).all()
    return [
        {"status": status, "count": count, "percentage": round((count / total * 100), 2) if total else 0}
        for status, count in rows
    ]

