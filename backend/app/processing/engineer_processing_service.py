from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from app.processing.engineer_excel_processor import EngineerExcelProcessor, EngineerRecordRepository


class EngineerProcessingService:
    """Service layer for engineer Excel processing.

    This layer is intentionally thin today, but it is the correct place to add
    future PostgreSQL transaction handling, repository calls, notifications, and
    audit logging without changing the pure processing engine.
    """

    def __init__(self, repository: Optional[EngineerRecordRepository] = None) -> None:
        self.repository = repository

    def process_excel_bytes(self, content: bytes, as_of_date: Optional[date] = None) -> Dict[str, Any]:
        processor = EngineerExcelProcessor(as_of_date=as_of_date)
        return processor.process_excel_bytes(content)

    def process_excel_file(self, file_path: str, as_of_date: Optional[date] = None) -> Dict[str, Any]:
        processor = EngineerExcelProcessor(as_of_date=as_of_date)
        return processor.process_excel_file(str(Path(file_path)))
