import argparse
from pathlib import Path

from fastapi import UploadFile

from app.db import Base, SessionLocal, engine
from app.routers.uploads import upload_engineers
from app.services import generate_monthly_snapshot, seed_reference_data


def is_month_end_today(today):
    from datetime import timedelta
    return (today + timedelta(days=1)).day == 1


async def run(file_path: str):
    from datetime import date

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_reference_data(db)
        path = Path(file_path)
        with path.open("rb") as handle:
            upload = UploadFile(filename=path.name, file=handle)
            result = await upload_engineers(upload, db)
        if is_month_end_today(date.today()):
            first_day = date.today().replace(day=1)
            generate_monthly_snapshot(db, first_day)
            db.commit()
        print(result.model_dump())
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Excel or CSV source file")
    args = parser.parse_args()
    asyncio.run(run(args.file))

