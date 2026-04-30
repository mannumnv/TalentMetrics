from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/pipeline-summary", response_model=List[schemas.PipelineSummaryItem])
def get_pipeline_summary(db: Session = Depends(get_db)):
    return services.pipeline_summary(db)

