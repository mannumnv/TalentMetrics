from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/pipeline-summary", response_model=List[schemas.PipelineSummaryItem])
def get_pipeline_summary(as_of_month: Optional[str] = None, as_of_year: Optional[int] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.pipeline_summary(db, as_of_month=as_of_month, category=category, as_of_year=as_of_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc



@router.get("/status-counts")
def get_status_counts(as_of_month: Optional[str] = None, as_of_year: Optional[int] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.status_counts(db, as_of_month=as_of_month, category=category, as_of_year=as_of_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc


@router.get("/monthly-trend", response_model=List[schemas.TrendItem])
def get_monthly_trend(year: Optional[int] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.monthly_trend(db, year=year, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc


@router.get("/year-comparison", response_model=List[schemas.YearComparisonItem])
def get_year_comparison(year: int, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        return services.year_comparison(db, year=year, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid filter", "details": str(exc)}) from exc
