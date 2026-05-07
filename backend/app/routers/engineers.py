from __future__ import annotations

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/engineers", tags=["engineers"])


def to_response(engineer: models.Engineer, derived_status: Optional[str] = None) -> schemas.EngineerResponse:
    return schemas.EngineerResponse(
        engineer_id=engineer.engineer_id,
        ite_number=engineer.ite_number,
        full_name=engineer.full_name,
        email=engineer.email,
        category=engineer.category.category_name,
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
def list_engineers(status: Optional[str] = None, category: Optional[str] = None, as_of_month: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(models.Engineer)
    if category:
        stmt = stmt.join(models.EngineerCategory).where(models.EngineerCategory.category_name == category)
    try:
        cutoff = services.month_end_from_yyyy_mm(as_of_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc
    if cutoff is not None:
        stmt = stmt.where(models.Engineer.date_of_joining.is_not(None)).where(models.Engineer.date_of_joining <= cutoff)
    engineers = db.scalars(stmt).unique().all()
    responses = []
    for engineer in engineers:
        derived = services.engineer_derived_status(db, engineer.ite_number, as_of_month)
        if status and status != "all" and derived != status:
            continue
        responses.append(to_response(engineer, derived_status=derived))
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

