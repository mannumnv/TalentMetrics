from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_IGNORED_SHEETS = {"テンプレ"}
ITE_HEADER_ALIASES = {"ite_no", "ite no", "ite_number", "ite number", "ite番号", "ｉｔｅ番号"}
ITE_COLUMN_ALIASES = ["ITE_NO", "ITE NO", "ITE_NUMBER", "ITE Number", "ITE番号", "ＩＴＥ番号"]


class ExcelIngestionError(ValueError):
    def __init__(self, message: str, details: str) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass(frozen=True)
class SheetIssue:
    sheet_name: str
    rule_code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"sheet_name": self.sheet_name, "rule_code": self.rule_code, "message": self.message}


def normalize_header(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).replace("\u3000", " ").strip().split())


def normalize_header_key(value: Any) -> str:
    return normalize_header(value).lower().replace("_", " ")


def is_unnamed_column(column_name: Any) -> bool:
    value = normalize_header(column_name)
    return not value or value.lower().startswith("unnamed:") or value.lower().startswith("unnamed_")


def find_header_row(raw_df: pd.DataFrame, required_aliases: Iterable[str] = ITE_HEADER_ALIASES) -> Optional[int]:
    aliases = {alias.lower().replace("_", " ") for alias in required_aliases}
    for index, row in raw_df.reset_index(drop=True).iterrows():
        values = {normalize_header_key(item) for item in row.tolist() if not pd.isna(item)}
        if values.intersection(aliases):
            return int(index)
    return None


def clean_sheet_dataframe(sheet_name: str, raw_df: pd.DataFrame, issues: List[SheetIssue]) -> pd.DataFrame:
    """Return a sheet DataFrame safe for concat/to_dict operations.

    The important invariant is: returned columns and index are unique.
    """
    if raw_df is None or raw_df.empty:
        issues.append(SheetIssue(sheet_name, "EMPTY_SHEET", "Sheet is empty and was skipped."))
        return pd.DataFrame()

    raw_df = raw_df.copy().reset_index(drop=True)
    header_index = find_header_row(raw_df)
    if header_index is None:
        issues.append(SheetIssue(sheet_name, "HEADER_NOT_FOUND", "No ITE_NO / ITE番号 header was found; sheet was skipped."))
        return pd.DataFrame()

    raw_columns = [normalize_header(item) for item in raw_df.iloc[header_index].tolist()]
    data_df = raw_df.iloc[header_index + 1 :].copy().reset_index(drop=True)
    data_df.columns = raw_columns

    # Drop blank/Unnamed columns first. This avoids duplicate blank labels later.
    keep_columns = [not is_unnamed_column(column) for column in data_df.columns]
    dropped_unnamed = len(keep_columns) - sum(keep_columns)
    if dropped_unnamed:
        issues.append(SheetIssue(sheet_name, "UNNAMED_COLUMNS_DROPPED", f"Dropped {dropped_unnamed} unnamed/blank columns."))
    data_df = data_df.loc[:, keep_columns]

    # Remove duplicate columns while preserving first occurrence. Duplicate labels are
    # the usual trigger for pandas 'Reindexing only valid with uniquely valued Index objects'.
    if data_df.columns.duplicated().any():
        duplicate_names = sorted({str(name) for name in data_df.columns[data_df.columns.duplicated()].tolist()})
        issues.append(SheetIssue(sheet_name, "DUPLICATE_COLUMNS_DROPPED", f"Dropped duplicate columns: {', '.join(duplicate_names)}"))
        data_df = data_df.loc[:, ~data_df.columns.duplicated(keep="first")]

    data_df = data_df.dropna(how="all").reset_index(drop=True)
    data_df["__source_sheet"] = sheet_name
    data_df["__source_row"] = data_df.index + header_index + 2

    # Final safety net: unique columns + unique index.
    data_df = data_df.loc[:, ~data_df.columns.duplicated(keep="first")].reset_index(drop=True)
    if not data_df.index.is_unique:
        data_df = data_df.reset_index(drop=True)

    logger.info("cleaned sheet=%s rows=%s columns=%s", sheet_name, len(data_df.index), list(data_df.columns))
    return data_df


def read_excel_sheets(content: bytes, file_name: Optional[str] = None, ignored_sheets: Optional[Sequence[str]] = None) -> Tuple[List[Tuple[str, pd.DataFrame]], List[SheetIssue]]:
    ignored = set(ignored_sheets or DEFAULT_IGNORED_SHEETS)
    issues: List[SheetIssue] = []
    try:
        workbook = pd.read_excel(BytesIO(content), sheet_name=None, header=None, dtype=object, engine="openpyxl")
    except Exception as exc:
        raise ExcelIngestionError("Invalid Excel format", str(exc)) from exc

    frames: List[Tuple[str, pd.DataFrame]] = []
    for sheet_name, raw_df in workbook.items():
        if normalize_header(sheet_name) in ignored:
            logger.info("ignored template sheet=%s", sheet_name)
            continue
        frame = clean_sheet_dataframe(sheet_name, raw_df, issues)
        if not frame.empty:
            frames.append((sheet_name, frame))
    return frames, issues


def read_csv_frame(content: bytes, file_name: Optional[str] = None) -> Tuple[List[Tuple[str, pd.DataFrame]], List[SheetIssue]]:
    issues: List[SheetIssue] = []
    try:
        raw_df = pd.read_csv(BytesIO(content), header=None, dtype=object)
    except Exception as exc:
        raise ExcelIngestionError("Invalid CSV format", str(exc)) from exc
    sheet_name = file_name or "csv"
    frame = clean_sheet_dataframe(sheet_name, raw_df, issues)
    return ([(sheet_name, frame)] if not frame.empty else []), issues


def concatenate_clean_frames(frames: List[Tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()

    safe_frames = []
    for _, frame in frames:
        safe_frame = frame.copy()
        safe_frame = safe_frame.loc[:, ~safe_frame.columns.duplicated(keep="first")].reset_index(drop=True)
        safe_frames.append(safe_frame)

    combined = pd.concat(safe_frames, ignore_index=True, sort=False, copy=False)
    combined = combined.loc[:, ~combined.columns.duplicated(keep="first")].reset_index(drop=True)
    logger.info("concatenated sheets=%s total_rows=%s unique_columns=%s", len(frames), len(combined.index), combined.columns.is_unique)
    return combined


def find_column(df: pd.DataFrame, aliases: Sequence[str]) -> Optional[str]:
    lookup = {normalize_header_key(alias): alias for alias in aliases}
    for column in df.columns:
        if normalize_header_key(column) in lookup:
            return column
    return None


def dedupe_by_ite_no(df: pd.DataFrame, issues: Optional[List[SheetIssue]] = None) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    ite_column = find_column(df, ITE_COLUMN_ALIASES)
    if not ite_column:
        raise ExcelIngestionError("Invalid Excel format", "Required ITE_NO / ITE番号 column is missing after sheet cleaning.")

    cleaned = df.copy().reset_index(drop=True)
    cleaned[ite_column] = cleaned[ite_column].map(lambda value: normalize_header(value) if not pd.isna(value) else None)
    before = len(cleaned.index)
    cleaned = cleaned[cleaned[ite_column].notna() & (cleaned[ite_column] != "")].reset_index(drop=True)
    missing_ite = before - len(cleaned.index)
    if missing_ite and issues is not None:
        issues.append(SheetIssue("ALL", "ROWS_WITHOUT_ITE_DROPPED", f"Dropped {missing_ite} rows without ITE_NO."))

    duplicate_count = int(cleaned.duplicated(subset=[ite_column], keep="last").sum())
    if duplicate_count and issues is not None:
        issues.append(SheetIssue("ALL", "DUPLICATE_ITE_DEDUPED", f"Deduped {duplicate_count} duplicate ITE_NO rows; latest row kept."))
    cleaned = cleaned.drop_duplicates(subset=[ite_column], keep="last").reset_index(drop=True)
    return cleaned


def keep_rows_with_ite_no(df: pd.DataFrame, issues: Optional[List[SheetIssue]] = None) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    ite_column = find_column(df, ITE_COLUMN_ALIASES)
    if not ite_column:
        raise ExcelIngestionError("Invalid Excel format", "Required ITE_NO / ITE番号 column is missing after sheet cleaning.")

    cleaned = df.copy().reset_index(drop=True)
    cleaned[ite_column] = cleaned[ite_column].map(lambda value: normalize_header(value) if not pd.isna(value) else None)
    before = len(cleaned.index)
    cleaned = cleaned[cleaned[ite_column].notna() & (cleaned[ite_column] != "")].reset_index(drop=True)
    missing_ite = before - len(cleaned.index)
    if missing_ite and issues is not None:
        issues.append(SheetIssue("ALL", "ROWS_WITHOUT_ITE_DROPPED", f"Dropped {missing_ite} rows without ITE_NO."))
    return cleaned


def read_tabular_upload(file_name: Optional[str], content: bytes) -> Tuple[pd.DataFrame, List[SheetIssue]]:
    if file_name and file_name.lower().endswith(".csv"):
        frames, issues = read_csv_frame(content, file_name)
    else:
        frames, issues = read_excel_sheets(content, file_name)

    combined = concatenate_clean_frames(frames)
    if combined.empty:
        raise ExcelIngestionError("Invalid Excel format", "No valid data sheets found. Template sheets are ignored.")
    cleaned = keep_rows_with_ite_no(combined, issues)
    return cleaned.reset_index(drop=True), issues
