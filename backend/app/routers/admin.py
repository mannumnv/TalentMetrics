from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit-logs", response_model=List[schemas.AuditLogResponse])
def audit_logs(db: Session = Depends(get_db)):
    return db.scalars(select(models.AuditLog).order_by(models.AuditLog.changed_at.desc()).limit(100)).all()


@router.get("/validation-runs")
def validation_runs(db: Session = Depends(get_db)):
    return db.scalars(select(models.ValidationRun).order_by(models.ValidationRun.started_at.desc()).limit(50)).all()


@router.get("/validation-runs/{run_id}/logs")
def validation_logs(run_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.ValidationLog).where(models.ValidationLog.validation_run_id == run_id)).all()

