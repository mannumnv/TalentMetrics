from __future__ import annotations

import hashlib
import logging
import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app import models


logger = logging.getLogger(__name__)

STATUS_ORDER = [
    "Training",
    "In Japan (Bench)",
    "Assigned (Pre-Join)",
    "Joined",
    "Historical",
]

DERIVED_STATUS_ORDER = ["Training", "Project Joined"]
DERIVED_STATUS_KEYS = {"Training": "training", "Project Joined": "project_joined"}


STATUS_KEYS = {
    "Training": "training",
    "In Japan (Bench)": "in_japan",
    "Assigned (Pre-Join)": "pre_join",
    "Joined": "joined",
    "Historical": "historical",
}

STATUS_ALIASES = {
    "": "Training",
    "training": "Training",
    "trainings": "Training",
    "研修": "Training",
    "in japan": "In Japan (Bench)",
    "in-japan": "In Japan (Bench)",
    "in japan bench": "In Japan (Bench)",
    "in japan (bench)": "In Japan (Bench)",
    "japan": "In Japan (Bench)",
    "bench": "In Japan (Bench)",
    "benched": "In Japan (Bench)",
    "待機": "In Japan (Bench)",
    "ベンチ": "In Japan (Bench)",
    "pre join": "Assigned (Pre-Join)",
    "pre-join": "Assigned (Pre-Join)",
    "prejoin": "Assigned (Pre-Join)",
    "assigned": "Assigned (Pre-Join)",
    "assigned pre join": "Assigned (Pre-Join)",
    "assigned (pre-join)": "Assigned (Pre-Join)",
    "アサイン": "Assigned (Pre-Join)",
    "joined": "Joined",
    "join": "Joined",
    "入場済": "Joined",
    "参画": "Joined",
    "historical": "Historical",
    "history": "Historical",
    "履歴": "Historical",
}


def normalize_status_name(raw_status: Any) -> str:
    if raw_status is None:
        return "Training"
    value = str(raw_status).strip().replace("\u3000", " ")
    key = " ".join(value.lower().replace("_", " ").replace("/", " ").split())
    key = key.replace("（", "(").replace("）", ")")
    return STATUS_ALIASES.get(key, value)


def status_key(status_name: str) -> str:
    return STATUS_KEYS.get(normalize_status_name(status_name), status_name.lower().replace(" ", "_"))

ALLOWED_TRANSITIONS = {
    "Training": {"In Japan (Bench)", "Historical"},
    "In Japan (Bench)": {"Assigned (Pre-Join)", "Historical"},
    "Assigned (Pre-Join)": {"Joined", "In Japan (Bench)", "Historical"},
    "Joined": {"In Japan (Bench)", "Historical"},
    "Historical": set(),
}



def month_end_from_yyyy_mm(month: Optional[str]) -> Optional[date]:
    if not month:
        return None
    try:
        year_text, month_text = month.split("-", 1)
        year = int(year_text)
        month_number = int(month_text)
        if month_number == 12:
            return date(year, 12, 31)
        next_month = date(year, month_number + 1, 1)
        return next_month - timedelta(days=1)
    except Exception as exc:
        raise ValueError("month must use YYYY-MM format") from exc


def month_start_from_yyyy_mm(month: str) -> date:
    try:
        year_text, month_text = month.split("-", 1)
        return date(int(year_text), int(month_text), 1)
    except Exception as exc:
        raise ValueError("month must use YYYY-MM format") from exc


def default_analysis_month(db: Session) -> str:
    latest = db.scalar(select(func.max(models.EngineerMonthlyPresence.source_month)))
    if latest:
        return str(latest)
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def default_last_year_start(as_of_month: str) -> date:
    end = month_end_from_yyyy_mm(as_of_month) or date.today()
    year = end.year - 1 if end.month < 12 else end.year
    month = end.month + 1 if end.month < 12 else 1
    return date(year, month, 1)


def derived_status_label(has_presence: bool) -> str:
    return "Training" if has_presence else "Project Joined"


def apply_analytics_filters(stmt: Any, as_of_month: Optional[str] = None, category: Optional[str] = None) -> Any:
    cutoff = month_end_from_yyyy_mm(as_of_month)
    if cutoff is not None:
        stmt = stmt.where(models.Engineer.date_of_joining.is_not(None)).where(models.Engineer.date_of_joining <= cutoff)
    if category:
        stmt = stmt.join(models.EngineerCategory, models.Engineer.category_id == models.EngineerCategory.category_id).where(models.EngineerCategory.category_name == category)
    return stmt


def seed_reference_data(db: Session) -> None:
    for name in ["Fresher", "Experienced"]:
        if not db.scalar(select(models.EngineerCategory).where(models.EngineerCategory.category_name == name)):
            db.add(models.EngineerCategory(category_name=name))

    for index, name in enumerate(STATUS_ORDER, start=1):
        if not db.scalar(select(models.StatusPipeline).where(models.StatusPipeline.status_name == name)):
            db.add(models.StatusPipeline(status_name=name, status_order=index, is_terminal=name == "Historical"))
    db.commit()


def categorize_engineer(total_experience_months: int) -> str:
    # HR rule: joining date <= 6 months ago is Fresher; greater than 6 months is Experienced.
    return "Experienced" if total_experience_months > 6 else "Fresher"


def get_category(db: Session, name: str) -> models.EngineerCategory:
    category = db.scalar(select(models.EngineerCategory).where(models.EngineerCategory.category_name == name))
    if not category:
        raise ValueError(f"Unknown category: {name}")
    return category


def get_status(db: Session, name: str) -> models.StatusPipeline:
    normalized_name = normalize_status_name(name)
    status = db.scalar(select(models.StatusPipeline).where(models.StatusPipeline.status_name == normalized_name))
    if not status:
        raise ValueError(f"Unknown status: {name}")
    return status


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def audit_log(db: Session, table_name: str, record_pk: str, action: str, old_data: Optional[dict], new_data: Optional[dict], changed_by: str, source_system: str) -> None:
    db.add(models.AuditLog(
        table_name=table_name,
        record_pk=record_pk,
        action=action,
        old_data=json_safe(old_data),
        new_data=json_safe(new_data),
        changed_by=changed_by,
        source_system=source_system,
    ))


def create_engineer(db: Session, payload: Any, changed_by: str = "API") -> models.Engineer:
    category = get_category(db, categorize_engineer(payload.total_experience_months))
    normalized_status = normalize_status_name(payload.current_status)
    status = get_status(db, normalized_status)
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
    to_status_name = normalize_status_name(to_status_name)
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


def sync_engineer_status_from_import(db: Session, engineer: models.Engineer, to_status_name: str, effective_from: date, reason: Optional[str], changed_by: str = "IMPORT") -> None:
    from_status_name = engineer.current_status.status_name
    to_status_name = normalize_status_name(to_status_name)
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
        "STATUS_IMPORT_SYNC",
        {"current_status": from_status_name},
        {"current_status": to_status_name},
        changed_by,
        "IMPORT_SYNC",
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


def derived_pipeline_summary(db: Session, as_of_month: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    selected_month = as_of_month or default_analysis_month(db)
    cutoff = month_end_from_yyyy_mm(selected_month)
    if cutoff is None:
        raise ValueError("month must use YYYY-MM format")
    start_date = None if as_of_month else default_last_year_start(selected_month)

    stmt = select(models.Engineer).join(models.EngineerCategory)
    stmt = stmt.where(models.Engineer.date_of_joining.is_not(None)).where(models.Engineer.date_of_joining <= cutoff)
    if start_date is not None:
        stmt = stmt.where(models.Engineer.date_of_joining >= start_date)
    if category:
        stmt = stmt.where(models.EngineerCategory.category_name == category)

    engineers = db.scalars(stmt).unique().all()
    present_ites = set(db.scalars(
        select(models.EngineerMonthlyPresence.ite_number)
        .where(models.EngineerMonthlyPresence.source_month == selected_month)
        .where(models.EngineerMonthlyPresence.was_present.is_(True))
    ).all())

    counts = {"Training": 0, "Project Joined": 0}
    for engineer in engineers:
        counts[derived_status_label(engineer.ite_number in present_ites)] += 1

    total = sum(counts.values())
    logger.info("derived_pipeline_summary month=%s category=%s total=%s counts=%s", selected_month, category, total, counts)
    return [
        {
            "status": label,
            "key": DERIVED_STATUS_KEYS[label],
            "count": counts[label],
            "percentage": round((counts[label] / total * 100), 2) if total else 0,
        }
        for label in DERIVED_STATUS_ORDER
    ]


def derived_status_counts(db: Session, as_of_month: Optional[str] = None, category: Optional[str] = None) -> Dict[str, int]:
    rows = derived_pipeline_summary(db, as_of_month=as_of_month, category=category)
    return {row["key"]: int(row["count"]) for row in rows}


def pipeline_summary(db: Session, as_of_month: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    return derived_pipeline_summary(db, as_of_month=as_of_month, category=category)


def status_counts(db: Session, as_of_month: Optional[str] = None, category: Optional[str] = None) -> Dict[str, int]:
    return derived_status_counts(db, as_of_month=as_of_month, category=category)


def engineer_derived_status(db: Session, ite_number: str, as_of_month: Optional[str]) -> str:
    selected_month = as_of_month or default_analysis_month(db)
    exists_row = db.scalar(
        select(models.EngineerMonthlyPresence.presence_id)
        .where(models.EngineerMonthlyPresence.ite_number == ite_number)
        .where(models.EngineerMonthlyPresence.source_month == selected_month)
        .where(models.EngineerMonthlyPresence.was_present.is_(True))
        .limit(1)
    )
    return derived_status_label(exists_row is not None)
