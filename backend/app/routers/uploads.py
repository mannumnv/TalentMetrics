from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


STATUS_ALIASES = {
    "training": "Training",
    "bench": "In Japan (Bench)",
    "in japan": "In Japan (Bench)",
    "in japan (bench)": "In Japan (Bench)",
    "prejoin": "Assigned (Pre-Join)",
    "pre-join": "Assigned (Pre-Join)",
    "assigned (pre-join)": "Assigned (Pre-Join)",
    "joined": "Joined",
    "historical": "Historical",
}


def value(row: Dict[str, Any], name: str) -> Any:
    item = row.get(name)
    if pd.isna(item):
        return None
    if isinstance(item, str):
        item = item.strip()
        return item or None
    return item


def first_value(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        item = value(row, name)
        if item is not None:
            return item
    return None


def parse_date(item: Any) -> Optional[date]:
    if not item:
        return None
    return pd.to_datetime(item).date()


def read_upload_dataframe(file_name: Optional[str], content: bytes) -> pd.DataFrame:
    if file_name and file_name.lower().endswith(".csv"):
        raw_df = pd.read_csv(BytesIO(content), header=None)
    else:
        raw_df = pd.read_excel(BytesIO(content), header=None)

    header_index = 0
    for index, row in raw_df.iterrows():
        values = {str(item).strip() for item in row.tolist() if not pd.isna(item)}
        if "ITE Number" in values or "ITE番号" in values:
            header_index = index
            break

    columns = [str(item).strip() if not pd.isna(item) else "" for item in raw_df.iloc[header_index].tolist()]
    df = raw_df.iloc[header_index + 1 :].copy()
    df.columns = columns
    df = df.dropna(how="all")

    ite_column = "ITE Number" if "ITE Number" in df.columns else "ITE番号" if "ITE番号" in df.columns else None
    if ite_column:
        df = df[df[ite_column].notna()]

    return df


def months_since(start_date: Optional[date]) -> int:
    if not start_date:
        return 0
    today = date.today()
    return max(0, (today.year - start_date.year) * 12 + today.month - start_date.month)


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    joining_date = parse_date(first_value(row, ["Date of Joining", "入社日"]))
    total_experience = first_value(row, ["Total Experience Months", "経験月数"])
    raw_status = str(first_value(row, ["Status", "ステータス"]) or "Training").strip().lower()
    return {
        "ite_number": first_value(row, ["ITE Number", "ITE番号"]),
        "full_name": first_value(row, ["Full Name", "名前"]),
        "email": (first_value(row, ["Email", "メール"]) or "").lower() or None,
        "total_experience_months": int(total_experience) if total_experience is not None else months_since(joining_date),
        "current_status": STATUS_ALIASES.get(raw_status, first_value(row, ["Status", "ステータス"]) or "Training"),
        "date_of_joining": joining_date,
        "japan_arrival_date": parse_date(first_value(row, ["Japan Arrival Date", "来日日"])),
        "primary_skill": first_value(row, ["Primary Skill", "スキル", "オフィス"]),
        "contract_start_date": parse_date(first_value(row, ["Contract Start Date", "契約開始日"])),
        "contract_end_date": parse_date(first_value(row, ["Contract End Date", "契約終了日"])),
    }


@router.post("/engineers", response_model=schemas.UploadResponse)
async def upload_engineers(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        df = read_upload_dataframe(file.filename, content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read upload: {exc}") from exc

    run = models.ValidationRun(run_name="manual_engineer_upload", source_file_name=file.filename, triggered_by="HR_USER")
    db.add(run)
    db.flush()

    inserted = updated = unchanged = errors = 0
    for index, raw_row in enumerate(df.to_dict(orient="records"), start=2):
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
            errors += 1
            services.add_validation_error(db, run.validation_run_id, index, ite_number, "Japan Arrival Date", "JAPAN_DATE_REQUIRED", "Japan arrival date is required")
            continue
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
                for field in ["full_name", "email", "total_experience_months", "japan_arrival_date", "primary_skill"]:
                    if getattr(engineer, field) != row[field]:
                        setattr(engineer, field, row[field])
                        changed = True
                if engineer.category_id != category.category_id:
                    engineer.category_id = category.category_id
                    changed = True
                if engineer.current_status.status_name != row["current_status"]:
                    services.update_engineer_status(db, engineer, row["current_status"], date.today(), "Upload sync", "UPLOAD")
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
    run.valid_records = len(df.index) - errors
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

