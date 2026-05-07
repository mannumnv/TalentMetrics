from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db
from app.processing.safe_excel import ExcelIngestionError, read_tabular_upload

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)


STATUS_ALIASES = services.STATUS_ALIASES


def value(row: Dict[str, Any], name: str) -> Any:
    item = row.get(name)
    if pd.isna(item):
        return None
    if isinstance(item, str):
        item = item.strip()
        return item or None
    return item


def as_text(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("\u3000", " ")
    return text or None


def as_email(value: Any) -> Optional[str]:
    text = as_text(value)
    return text.lower() if text else None


def first_value(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        item = value(row, name)
        if item is not None:
            return item
    return None


def parse_date(item: Any) -> Optional[date]:
    if item is None or pd.isna(item):
        return None
    parsed = pd.to_datetime(item, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def read_upload_dataframe(file_name: Optional[str], content: bytes) -> pd.DataFrame:
    df, sheet_issues = read_tabular_upload(file_name, content)
    for issue in sheet_issues:
        logger.warning("upload ingestion issue sheet=%s rule=%s message=%s", issue.sheet_name, issue.rule_code, issue.message)
    logger.info("upload parsed file=%s rows=%s columns=%s", file_name, len(df.index), list(df.columns))
    return df


def months_since(start_date: Optional[date]) -> int:
    if not start_date:
        return 0
    today = date.today()
    return max(0, (today.year - start_date.year) * 12 + today.month - start_date.month)


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    joining_date = parse_date(first_value(row, ["Date of Joining", "JOIN_DATE", "JOIN DATE", "入社日", "入場日"]))
    total_experience = first_value(row, ["Total Experience Months", "経験月数"])
    raw_status = first_value(row, ["Status", "ステータス", "状態", "状況", "STATUS"])
    return {
        "ite_number": as_text(first_value(row, ["ITE Number", "ITE番号", "ITE_NO", "ITE NO", "ITE_NUMBER"])),
        "full_name": as_text(first_value(row, ["Full Name", "名前", "氏名", "Name"])),
        "email": as_email(first_value(row, ["Email", "メール"])),
        "total_experience_months": int(total_experience) if total_experience is not None else months_since(joining_date),
        "current_status": services.normalize_status_name(raw_status),
        "date_of_joining": joining_date,
        "japan_arrival_date": parse_date(first_value(row, ["Japan Arrival Date", "来日日"])),
        "primary_skill": as_text(first_value(row, ["Primary Skill", "スキル", "オフィス"])),
        "contract_start_date": parse_date(first_value(row, ["Contract Start Date", "CONTRACT_START", "CONTRACT START", "契約開始日"])),
        "contract_end_date": parse_date(first_value(row, ["Contract End Date", "CONTRACT_END", "CONTRACT END", "契約終了日"])),
    }


def infer_source_month(row: Dict[str, Any]) -> Optional[str]:
    sheet = str(row.get("__source_sheet") or "")
    match = re.search(r"(20\d{2})年\s*(\d{1,2})月", sheet) or re.search(r"(20\d{2})[-_/](\d{1,2})", sheet)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"

    for column in row.keys():
        text = str(column).strip()
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})", text)
        if match:
            return f"{date.today().year:04d}-{int(match.group(1)):02d}"
    return None


def record_monthly_presence(db: Session, rows: List[Dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    for raw_row in rows:
        normalized = normalize_row(raw_row)
        ite_number = normalized.get("ite_number")
        source_month = infer_source_month(raw_row)
        if not ite_number or not source_month:
            continue
        key = (str(ite_number), source_month)
        if key in seen:
            continue
        seen.add(key)
        existing = db.scalar(
            select(models.EngineerMonthlyPresence)
            .where(models.EngineerMonthlyPresence.ite_number == str(ite_number))
            .where(models.EngineerMonthlyPresence.source_month == source_month)
        )
        if existing:
            existing.was_present = True
            existing.source_sheet = str(raw_row.get("__source_sheet") or "")
            existing.source_row = int(raw_row.get("__source_row") or 0) or None
        else:
            db.add(models.EngineerMonthlyPresence(
                ite_number=str(ite_number),
                source_month=source_month,
                source_sheet=str(raw_row.get("__source_sheet") or ""),
                source_row=int(raw_row.get("__source_row") or 0) or None,
                was_present=True,
            ))
    logger.info("recorded monthly presence rows=%s unique=%s", len(rows), len(seen))


def add_validation_warning(db: Session, run_id: int, row_number: Optional[int], ite_number: Optional[str], field: str, rule_code: str, message: str, invalid_value: Any = None) -> None:
    db.add(models.ValidationLog(
        validation_run_id=run_id,
        severity="WARNING",
        entity_type="Engineer",
        ite_number=ite_number,
        field_name=field,
        invalid_value=None if invalid_value is None else str(invalid_value),
        rule_code=rule_code,
        message=message,
        row_number=row_number,
    ))


def dedupe_latest_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for position, row in enumerate(rows):
        row["__source_position"] = position
        normalized = normalize_row(row)
        ite_number = normalized.get("ite_number")
        if ite_number:
            deduped[str(ite_number)] = row
        else:
            deduped[f"__invalid_{position}"] = row
    return list(deduped.values())


@router.post("/engineers", response_model=schemas.UploadResponse)
async def upload_engineers(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        df = read_upload_dataframe(file.filename, content)
    except ExcelIngestionError as exc:
        logger.exception("upload ingestion failed file=%s details=%s", file.filename, exc.details)
        raise HTTPException(status_code=400, detail={"status": "error", "message": exc.message, "details": exc.details}) from exc
    except Exception as exc:
        logger.exception("unexpected upload ingestion failure file=%s", file.filename)
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid Excel format", "details": str(exc)}) from exc

    run = models.ValidationRun(run_name="manual_engineer_upload", source_file_name=file.filename, triggered_by="HR_USER")
    db.add(run)
    db.flush()

    inserted = updated = unchanged = errors = 0
    all_rows = df.to_dict(orient="records")
    record_monthly_presence(db, all_rows)
    raw_rows = dedupe_latest_rows(all_rows)
    logger.info("upload normalized rows=%s deduped_rows=%s", len(df.index), len(raw_rows))
    for index, raw_row in enumerate(raw_rows, start=2):
        row = normalize_row(raw_row)
        row_hash = services.source_hash(row)
        ite_number = row["ite_number"]

        if not ite_number:
            errors += 1
            services.add_validation_error(db, run.validation_run_id, index, None, "ITE Number", "ITE_REQUIRED", "ITE Number is required")
            continue
        if not row["full_name"]:
            errors += 1
            services.add_validation_error(db, run.validation_run_id, index, ite_number, "Full Name", "NAME_REQUIRED", "Full Name is required")
            continue
        if row["current_status"] in {"In Japan (Bench)", "Assigned (Pre-Join)", "Joined"} and not row["japan_arrival_date"]:
            add_validation_warning(db, run.validation_run_id, index, ite_number, "Japan Arrival Date", "JAPAN_DATE_MISSING", "Japan arrival date is missing; row was still imported because status analytics should not be blocked.")
        if row["contract_start_date"] and row["contract_end_date"] and row["contract_end_date"] < row["contract_start_date"]:
            errors += 1
            services.add_validation_error(db, run.validation_run_id, index, ite_number, "Contract End Date", "CONTRACT_DATE_INVALID", "Contract end date must be after start date")
            continue

        state = db.get(models.EngineerSourceState, ite_number)
        if state and state.last_source_hash == row_hash:
            unchanged += 1
            continue

        try:
            engineer = db.scalar(select(models.Engineer).where(models.Engineer.ite_number == ite_number))
            category = services.get_category(db, services.categorize_engineer(row["total_experience_months"]))
            if not engineer:
                payload = schemas.EngineerCreate(**{k: row[k] for k in ["ite_number", "full_name", "email", "total_experience_months", "current_status", "date_of_joining", "japan_arrival_date", "primary_skill"]})
                engineer = services.create_engineer(db, payload, changed_by="UPLOAD")
                inserted += 1
            else:
                old_data = {
                    "full_name": engineer.full_name,
                    "email": engineer.email,
                    "category_id": engineer.category_id,
                    "primary_skill": engineer.primary_skill,
                }
                changed = False
                for field in ["full_name", "email", "total_experience_months", "date_of_joining", "japan_arrival_date", "primary_skill"]:
                    if getattr(engineer, field) != row[field]:
                        setattr(engineer, field, row[field])
                        changed = True
                if engineer.category_id != category.category_id:
                    engineer.category_id = category.category_id
                    changed = True
                if engineer.current_status.status_name != row["current_status"]:
                    services.sync_engineer_status_from_import(db, engineer, row["current_status"], date.today(), "Upload sync", "UPLOAD")
                    changed = True
                if changed:
                    engineer.updated_at = datetime.utcnow()
                    services.audit_log(db, "engineers", str(engineer.engineer_id), "UPDATE", old_data, row, "UPLOAD", "MANUAL_UPLOAD")
                    updated += 1
                else:
                    unchanged += 1

            if row["contract_start_date"] and row["contract_end_date"]:
                contract = db.scalar(
                    select(models.Contract)
                    .where(models.Contract.engineer_id == engineer.engineer_id)
                    .where(models.Contract.contract_start_date == row["contract_start_date"])
                )
                if not contract:
                    db.add(models.Contract(
                        engineer_id=engineer.engineer_id,
                        contract_start_date=row["contract_start_date"],
                        contract_end_date=row["contract_end_date"],
                    ))
                elif row["contract_end_date"] > contract.contract_end_date:
                    old_end = contract.contract_end_date
                    db.add(models.ContractExtension(contract_id=contract.contract_id, previous_end_date=old_end, new_end_date=row["contract_end_date"], extension_reason="Upload sync"))
                    contract.contract_end_date = row["contract_end_date"]
                    contract.contract_status = "Extended"

            if not state:
                state = models.EngineerSourceState(ite_number=ite_number, last_source_hash=row_hash)
                db.add(state)
            state.last_source_hash = row_hash
            db.flush()
        except Exception as exc:
            errors += 1
            db.rollback()
            db.add(run)
            services.add_validation_error(db, run.validation_run_id, index, ite_number, "row", "PROCESSING_ERROR", str(exc))

    run.total_records = len(df.index)
    run.valid_records = len(raw_rows) - errors
    run.error_records = errors
    run.completed_at = datetime.utcnow()
    run.run_status = "Failed" if errors else "Passed"
    db.commit()
    return schemas.UploadResponse(
        validation_run_id=run.validation_run_id,
        total_records=run.total_records,
        inserted_records=inserted,
        updated_records=updated,
        unchanged_records=unchanged,
        error_records=errors,
    )

