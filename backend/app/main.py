from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routers import admin, analytics, auth, engineers, processing, uploads
from app.services import seed_reference_data

app = FastAPI(title="HR Analytics API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_reference_data(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(engineers.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(uploads.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(analytics.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(processing.router, dependencies=[Depends(auth.get_current_user)])
app.include_router(admin.router, dependencies=[Depends(auth.get_current_user)])
