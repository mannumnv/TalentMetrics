from __future__ import annotations

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/engineers", tags=["engineers"])


def to_response(engineer: models.Engineer, derived_status: Optional[str] = None, as_of_month: Optional[str] = None, category_override: Optional[str] = None) -> schemas.EngineerResponse:
    return schemas.EngineerResponse(
        engineer_id=engineer.engineer_id,
        ite_number=engineer.ite_number,
        full_name=engineer.full_name,
        email=engineer.email,
        category=category_override or services.experience_category_as_of(engineer, as_of_month),
        current_status=derived_status or engineer.current_status.status_name,
        total_experience_months=engineer.total_experience_months,
        date_of_joining=engineer.date_of_joining,
    )


@router.post("", response_model=schemas.EngineerResponse)
def create_engineer(payload: schemas.EngineerCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(models.Engineer).where(models.Engineer.ite_number == payload.ite_number))
    if existing:
        raise HTTPException(status_code=409, detail="ITE Number already exists")
    try:
        engineer = services.create_engineer(db, payload)
        db.commit()
        db.refresh(engineer)
        return to_response(engineer)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[schemas.EngineerResponse])
def list_engineers(status: Optional[str] = None, category: Optional[str] = None, as_of_month: Optional[str] = None, as_of_year: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        services.validate_not_future_month(as_of_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc

    if as_of_month:
        selected_ites = services.presence_ites_for_month(db, as_of_month)
        previous_month = services.previous_month_yyyy_mm(as_of_month)
        previous_ites = services.presence_ites_for_month(db, previous_month)
        if status == "Project Joined":
            candidate_ites = previous_ites - selected_ites
        elif status == "Training":
            candidate_ites = selected_ites
        else:
            candidate_ites = selected_ites | previous_ites
        stmt = (
            select(models.Engineer)
            .where(models.Engineer.ite_number.in_(candidate_ites))
        )
    elif as_of_year:
        year_ites = set()
        project_joined_ites = set()
        for month_number in range(1, 13):
            month = services.year_month_value(as_of_year, month_number)
            current_ites = services.presence_ites_for_month(db, month)
            previous_ites = services.presence_ites_for_month(db, services.previous_month_yyyy_mm(month))
            year_ites.update(current_ites)
            project_joined_ites.update(previous_ites - current_ites)
        candidate_ites = project_joined_ites if status == "Project Joined" else year_ites
        stmt = select(models.Engineer).where(models.Engineer.ite_number.in_(candidate_ites))
    else:
        stmt = select(models.Engineer)

    engineers = db.scalars(stmt).unique().all()
    if as_of_month:
        selected_ites = services.presence_ites_for_month(db, as_of_month)
    elif as_of_year:
        selected_ites = year_ites
    else:
        selected_ites = set()
        previous_month = None
    responses = []
    selected_join_dates = services.monthly_record_join_dates(db, as_of_month) if as_of_month else {}
    previous_join_dates = services.monthly_record_join_dates(db, previous_month) if previous_month else {}
    for engineer in engineers:
        if as_of_month:
            if engineer.ite_number in selected_ites:
                derived = "Training"
                joining_date = selected_join_dates.get(engineer.ite_number)
            else:
                derived = "Project Joined"
                joining_date = previous_join_dates.get(engineer.ite_number)
            if joining_date:
                as_of_date = services.month_end_from_yyyy_mm(as_of_month)
                category_label = services.experience_category_label(services.months_between(joining_date, as_of_date)) if as_of_date else services.experience_category_as_of(engineer, as_of_month)
            else:
                category_label = services.experience_category_as_of(engineer, as_of_month)
        else:
            derived = "Training"
            selected_for_category = f"{as_of_year}-12" if as_of_year else as_of_month
            derived = "Project Joined" if as_of_year and engineer.ite_number in project_joined_ites and status == "Project Joined" else derived
            category_label = services.experience_category_as_of(engineer, selected_for_category)
        if category and category_label != category:
            continue
        if status and status != "all" and derived != status:
            continue
        responses.append(to_response(engineer, derived_status=derived, as_of_month=as_of_month, category_override=category_label))
    return responses


@router.get("/{ite_number}", response_model=schemas.EngineerResponse)
def get_engineer(ite_number: str, db: Session = Depends(get_db)):
    engineer = db.scalar(select(models.Engineer).where(models.Engineer.ite_number == ite_number))
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer not found")
    return to_response(engineer)


@router.post("/{ite_number}/status", response_model=schemas.StatusUpdateResponse)
def update_status(ite_number: str, payload: schemas.StatusUpdateRequest, db: Session = Depends(get_db)):
    engineer = db.scalar(select(models.Engineer).where(models.Engineer.ite_number == ite_number))
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer not found")
    from_status = engineer.current_status.status_name
    try:
        services.update_engineer_status(db, engineer, payload.to_status, payload.effective_from, payload.reason)
        db.commit()
        return schemas.StatusUpdateResponse(
            ite_number=ite_number,
            from_status=from_status,
            to_status=payload.to_status,
            effective_from=payload.effective_from,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
