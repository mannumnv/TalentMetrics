from __future__ import annotations

import argparse
import json

from app.processing.engineer_processing_service import EngineerProcessingService


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process multi-sheet engineer Excel and print analytics JSON.")
    parser.add_argument("--file", required=True, help="Path to .xlsx/.xlsm/.xls file")
    args = parser.parse_args()

    result = EngineerProcessingService().process_excel_file(args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
