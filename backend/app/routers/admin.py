from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.routers.auth import get_current_user, record_activity

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(user: models.AppUser = Depends(get_current_user)) -> models.AppUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/audit-logs", response_model=List[schemas.AuditLogResponse])
def audit_logs(_admin: models.AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(models.AuditLog).order_by(models.AuditLog.changed_at.desc()).limit(100)).all()


@router.get("/user-activity", response_model=List[schemas.UserActivityLogResponse])
def user_activity(current_user: models.AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(models.UserActivityLog)
    if current_user.role != "admin":
        stmt = stmt.where(models.UserActivityLog.user_id == current_user.user_id)
    stmt = stmt.order_by(models.UserActivityLog.timestamp.desc()).limit(200)
    return db.scalars(stmt).all()


@router.get("/users", response_model=List[schemas.AdminUserResponse])
def users(current_user: models.AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        return [current_user]
    return db.scalars(select(models.AppUser).order_by(models.AppUser.created_at.desc())).all()


@router.patch("/users/{user_id}/dob", response_model=schemas.AdminUserResponse)
def update_user_dob(user_id: int, payload: schemas.DobUpdateRequest, admin: models.AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(models.AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.dob = payload.dob
    record_activity(db, admin, f"UPDATE_DOB {user.email}")
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def remove_user(user_id: int, admin: models.AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(models.AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Admin cannot remove own account")

    email = user.email
    db.query(models.UserActivityLog).filter(models.UserActivityLog.user_id == user.user_id).update({"user_id": None})
    db.query(models.UserSession).filter(models.UserSession.user_id == user.user_id).delete()
    db.delete(user)
    record_activity(db, admin, f"REMOVE_USER {email}")
    db.commit()
    return {"status": "ok", "removed_user": email}


@router.get("/validation-runs")
def validation_runs(db: Session = Depends(get_db)):
    return db.scalars(select(models.ValidationRun).order_by(models.ValidationRun.started_at.desc()).limit(50)).all()


@router.get("/validation-runs/{run_id}/logs")
def validation_logs(run_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.ValidationLog).where(models.ValidationLog.validation_run_id == run_id)).all()
