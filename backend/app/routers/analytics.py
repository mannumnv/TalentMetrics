from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/pipeline-summary", response_model=List[schemas.PipelineSummaryItem])
def get_pipeline_summary(as_of_month: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.pipeline_summary(db, as_of_month=as_of_month, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc



@router.get("/status-counts")
def get_status_counts(as_of_month: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.status_counts(db, as_of_month=as_of_month, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc
