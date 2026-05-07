from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

import pandas as pd

from app.processing.safe_excel import ExcelIngestionError, SheetIssue, read_tabular_upload


CANONICAL_FIELDS = [
    "ITE_NO",
    "JOIN_DATE",
    "CONTRACT_START",
    "CONTRACT_END",
    "STATUS",
    "YEAR",
    "MONTH",
    "CLASSIFICATION",
    "TENURE_BUCKET",
]

COLUMN_ALIASES = {
    "ITE_NO": {
        "ITE_NO",
        "ITE NO",
        "ITE_NUMBER",
        "ITE NUMBER",
        "ITE番号",
        "ＩＴＥ番号",
        "ITE No",
        "ITE No.",
    },
    "JOIN_DATE": {
        "JOIN_DATE",
        "JOIN DATE",
        "DATE_OF_JOINING",
        "DATE OF JOINING",
        "入社日",
        "入場日",
        "JOINING DATE",
    },
    "CONTRACT_START": {
        "CONTRACT_START",
        "CONTRACT START",
        "CONTRACT_START_DATE",
        "CONTRACT START DATE",
        "契約開始日",
        "契約開始",
    },
    "CONTRACT_END": {
        "CONTRACT_END",
        "CONTRACT END",
        "CONTRACT_END_DATE",
        "CONTRACT END DATE",
        "契約終了日",
        "契約終了",
    },
    "STATUS": {
        "STATUS",
        "ステータス",
        "状態",
        "状況",
    },
}

STATUS_ALIASES = {
    "training": "Training",
    "研修": "Training",
    "bench": "In Japan (Bench)",
    "in japan": "In Japan (Bench)",
    "in japan (bench)": "In Japan (Bench)",
    "待機": "In Japan (Bench)",
    "ベンチ": "In Japan (Bench)",
    "prejoin": "Assigned (Pre-Join)",
    "pre-join": "Assigned (Pre-Join)",
    "assigned (pre-join)": "Assigned (Pre-Join)",
    "アサイン": "Assigned (Pre-Join)",
    "joined": "Joined",
    "参画": "Joined",
    "入場済": "Joined",
    "historical": "Historical",
    "履歴": "Historical",
}

REQUIRED_FIELDS = {"ITE_NO", "JOIN_DATE"}


@dataclass(frozen=True)
class InvalidRecord:
    sheet_name: str
    row_number: int
    ite_no: Optional[str]
    field_name: str
    rule_code: str
    message: str
    raw_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "row_number": self.row_number,
            "ite_no": self.ite_no,
            "field_name": self.field_name,
            "rule_code": self.rule_code,
            "message": self.message,
            "raw_value": self.raw_value,
        }


@dataclass(frozen=True)
class EngineerRecord:
    ite_no: str
    join_date: date
    contract_start: Optional[date]
    contract_end: Optional[date]
    status: Optional[str]
    source_sheet: str
    source_row_number: int
    source_position: int
    source_hash: str

    @property
    def year(self) -> str:
        return f"{self.join_date.year:04d}"

    @property
    def month(self) -> str:
        return self.join_date.strftime("%Y-%m")

    def classification(self, as_of_date: date) -> str:
        return "Fresher" if months_between(self.join_date, as_of_date) < 12 else "Experienced"

    def tenure_bucket(self, as_of_date: date) -> str:
        tenure_months = months_between(self.join_date, as_of_date)
        if tenure_months < 12:
            return "New Joiner"
        if tenure_months < 24:
            return "Junior"
        if tenure_months < 60:
            return "Mid"
        return "Senior"

    def to_standard_dict(self, as_of_date: date) -> Dict[str, Any]:
        return {
            "ITE_NO": self.ite_no,
            "JOIN_DATE": self.join_date.isoformat(),
            "CONTRACT_START": self.contract_start.isoformat() if self.contract_start else None,
            "CONTRACT_END": self.contract_end.isoformat() if self.contract_end else None,
            "STATUS": self.status,
            "YEAR": self.year,
            "MONTH": self.month,
            "CLASSIFICATION": self.classification(as_of_date),
            "TENURE_BUCKET": self.tenure_bucket(as_of_date),
            "SOURCE_HASH": self.source_hash,
        }


class EngineerRecordRepository(Protocol):
    """Future PostgreSQL upsert contract.

    Implement this with SQLAlchemy later. The processor already emits stable ITE_NO
    keys and source_hash values, so DB writes can be idempotent.
    """

    def upsert_engineer_records(self, records: Iterable[EngineerRecord]) -> None:
        ...


class EngineerExcelProcessor:
    def __init__(self, as_of_date: Optional[date] = None) -> None:
        self.as_of_date = as_of_date or date.today()

    def process_excel_bytes(self, content: bytes) -> Dict[str, Any]:
        df, sheet_issues = read_tabular_upload("upload.xlsx", content)
        return self._process_dataframe(df, sheet_issues)

    def process_excel_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "rb") as handle:
            df, sheet_issues = read_tabular_upload(file_path, handle.read())
        return self._process_dataframe(df, sheet_issues)

    def _process_dataframe(self, df: pd.DataFrame, sheet_issues: List[SheetIssue]) -> Dict[str, Any]:
        invalid_records: List[InvalidRecord] = [
            InvalidRecord(
                sheet_name=issue.sheet_name,
                row_number=0,
                ite_no=None,
                field_name="SHEET",
                rule_code=issue.rule_code,
                message=issue.message,
            )
            for issue in sheet_issues
        ]
        column_map = build_column_map([normalize_header(column) for column in df.columns.tolist()])
        missing = REQUIRED_FIELDS.difference(column_map.keys())
        if missing:
            invalid_records.append(InvalidRecord(
                sheet_name="ALL",
                row_number=0,
                ite_no=None,
                field_name="HEADER",
                rule_code="REQUIRED_COLUMNS_MISSING",
                message=f"Missing required columns: {', '.join(sorted(missing))}",
            ))
            return {
                "monthly_summary": {},
                "yearly_summary": {},
                "tenure_distribution": {"New Joiner": 0, "Junior": 0, "Mid": 0, "Senior": 0},
                "invalid_records_log": [item.to_dict() for item in invalid_records],
            }

        deduped_records: Dict[str, EngineerRecord] = {}
        for position, row in enumerate(df.to_dict(orient="records"), start=1):
            sheet_name = clean_text(row.get("__source_sheet")) or "ALL"
            row_number = int(row.get("__source_row") or position)
            record, row_errors = self._normalize_record(row, column_map, sheet_name, row_number, position)
            invalid_records.extend(row_errors)
            if record is not None:
                deduped_records[record.ite_no] = record

        records = list(deduped_records.values())
        return {
            "monthly_summary": self._monthly_summary(records),
            "yearly_summary": self._yearly_summary(records),
            "tenure_distribution": self._tenure_distribution(records),
            "invalid_records_log": [item.to_dict() for item in invalid_records],
        }

    def _process_sheets(self, sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        invalid_records: List[InvalidRecord] = []
        deduped_records: Dict[str, EngineerRecord] = {}
        source_position = 0

        for sheet_name, raw_df in sheets.items():
            header_row_index, column_map = self._detect_header(raw_df)
            if header_row_index is None:
                invalid_records.append(InvalidRecord(
                    sheet_name=sheet_name,
                    row_number=0,
                    ite_no=None,
                    field_name="HEADER",
                    rule_code="HEADER_NOT_FOUND",
                    message="No supported header row found. Expected ITE_NO/ITE番号 and JOIN_DATE/入社日.",
                ))
                continue

            data_df = raw_df.iloc[header_row_index + 1 :].copy()
            headers = [normalize_header(item) for item in raw_df.iloc[header_row_index].tolist()]
            data_df.columns = headers
            data_df = data_df.dropna(how="all")

            for relative_index, row in enumerate(data_df.to_dict(orient="records"), start=1):
                source_position += 1
                excel_row_number = int(header_row_index + relative_index + 1)
                record, row_errors = self._normalize_record(row, column_map, sheet_name, excel_row_number, source_position)
                invalid_records.extend(row_errors)
                if record is None:
                    continue

                # Latest record wins by physical workbook order, never by sheet name/month.
                existing = deduped_records.get(record.ite_no)
                if existing is None or record.source_position >= existing.source_position:
                    deduped_records[record.ite_no] = record

        records = list(deduped_records.values())
        return {
            "monthly_summary": self._monthly_summary(records),
            "yearly_summary": self._yearly_summary(records),
            "tenure_distribution": self._tenure_distribution(records),
            "invalid_records_log": [item.to_dict() for item in invalid_records],
        }

    def _detect_header(self, raw_df: pd.DataFrame) -> Tuple[Optional[int], Dict[str, str]]:
        for index, row in raw_df.iterrows():
            normalized_headers = [normalize_header(item) for item in row.tolist()]
            column_map = build_column_map(normalized_headers)
            if REQUIRED_FIELDS.issubset(column_map.keys()):
                return int(index), column_map
        return None, {}

    def _normalize_record(
        self,
        row: Dict[str, Any],
        column_map: Dict[str, str],
        sheet_name: str,
        row_number: int,
        source_position: int,
    ) -> Tuple[Optional[EngineerRecord], List[InvalidRecord]]:
        errors: List[InvalidRecord] = []
        ite_no = clean_text(row.get(column_map.get("ITE_NO", "")))
        join_date_value = row.get(column_map.get("JOIN_DATE", ""))

        if not ite_no:
            errors.append(InvalidRecord(sheet_name, row_number, None, "ITE_NO", "ITE_NO_REQUIRED", "ITE_NO is required."))
            return None, errors

        join_date = parse_excel_date(join_date_value)
        if join_date is None:
            errors.append(InvalidRecord(
                sheet_name,
                row_number,
                ite_no,
                "JOIN_DATE",
                "JOIN_DATE_REQUIRED_OR_INVALID",
                "JOIN_DATE is missing or invalid. This row was skipped because JOIN_DATE is the source of truth.",
                raw_value=stringify(join_date_value),
            ))
            return None, errors

        contract_start = parse_excel_date(row.get(column_map.get("CONTRACT_START", "")))
        contract_end = parse_excel_date(row.get(column_map.get("CONTRACT_END", "")))
        status = normalize_status(clean_text(row.get(column_map.get("STATUS", ""))))

        if contract_start and contract_end and contract_end < contract_start:
            errors.append(InvalidRecord(
                sheet_name,
                row_number,
                ite_no,
                "CONTRACT_END",
                "CONTRACT_DATE_INVALID",
                "CONTRACT_END cannot be before CONTRACT_START.",
                raw_value=contract_end.isoformat(),
            ))

        source_hash = stable_hash({
            "ITE_NO": ite_no,
            "JOIN_DATE": join_date.isoformat(),
            "CONTRACT_START": contract_start.isoformat() if contract_start else None,
            "CONTRACT_END": contract_end.isoformat() if contract_end else None,
            "STATUS": status,
        })

        return EngineerRecord(
            ite_no=ite_no,
            join_date=join_date,
            contract_start=contract_start,
            contract_end=contract_end,
            status=status,
            source_sheet=sheet_name,
            source_row_number=row_number,
            source_position=source_position,
            source_hash=source_hash,
        ), errors

    def _monthly_summary(self, records: List[EngineerRecord]) -> Dict[str, Any]:
        current_year = self.as_of_date.year
        summary: Dict[str, Dict[str, int]] = {}
        for record in records:
            if record.join_date.year != current_year:
                continue
            month = record.month
            classification = record.classification(self.as_of_date)
            bucket = summary.setdefault(month, {"total_joinees": 0, "freshers": 0, "experienced": 0})
            bucket["total_joinees"] += 1
            if classification == "Fresher":
                bucket["freshers"] += 1
            else:
                bucket["experienced"] += 1
        return dict(sorted(summary.items()))

    def _yearly_summary(self, records: List[EngineerRecord]) -> Dict[str, Any]:
        summary: Dict[str, Dict[str, int]] = {}
        for record in records:
            year = record.year
            classification = record.classification(self.as_of_date)
            bucket = summary.setdefault(year, {"total_joinees": 0, "freshers": 0, "experienced": 0})
            bucket["total_joinees"] += 1
            if classification == "Fresher":
                bucket["freshers"] += 1
            else:
                bucket["experienced"] += 1
        return dict(sorted(summary.items()))

    def _tenure_distribution(self, records: List[EngineerRecord]) -> Dict[str, int]:
        distribution = {"New Joiner": 0, "Junior": 0, "Mid": 0, "Senior": 0}
        for record in records:
            distribution[record.tenure_bucket(self.as_of_date)] += 1
        return distribution


def build_column_map(headers: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for header in headers:
        if not header:
            continue
        for canonical, aliases in COLUMN_ALIASES.items():
            normalized_aliases = {normalize_header(alias) for alias in aliases}
            if header in normalized_aliases:
                result[canonical] = header
    return result


def normalize_header(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().replace("\u3000", " ").upper()


def clean_text(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("\u3000", " ")
    return text or None


def parse_excel_date(value: Any) -> Optional[date]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def normalize_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return STATUS_ALIASES.get(value.strip().lower(), value.strip())


def months_between(start_date: date, end_date: date) -> int:
    months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
    if end_date.day < start_date.day:
        months -= 1
    return max(0, months)


def stable_hash(values: Dict[str, Any]) -> str:
    payload = "|".join(f"{key}={values.get(key) or ''}" for key in sorted(values.keys()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stringify(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    return str(value)
