from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.processing.engineer_processing_service import EngineerProcessingService

router = APIRouter(prefix="/api/v1/processing", tags=["processing"])


@router.post("/engineer-excel")
async def process_engineer_excel(file: UploadFile = File(...), as_of_date: Optional[date] = None):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload a multi-sheet Excel file (.xlsx, .xlsm, .xls).")

    content = await file.read()
    try:
        return EngineerProcessingService().process_excel_bytes(content, as_of_date=as_of_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to process engineer Excel file: {exc}") from exc
