from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import GoogleAuthUrlResponse, GoogleConnectionStatus, GoogleSyncResponse
from app.services.google_calendar_service import (
    build_google_auth_url,
    exchange_google_code,
    google_connection_status,
    sync_day_to_google,
)

router = APIRouter(prefix="/google", tags=["google-calendar"])


@router.get("/status", response_model=GoogleConnectionStatus)
def status_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GoogleConnectionStatus:
    return google_connection_status(db, current_user)


@router.get("/auth-url", response_model=GoogleAuthUrlResponse)
def auth_url_endpoint(
    current_user: User = Depends(get_current_user),
) -> GoogleAuthUrlResponse:
    auth_url, state = build_google_auth_url(current_user)
    return GoogleAuthUrlResponse(auth_url=auth_url, state=state)


@router.get("/callback")
def callback_endpoint(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    exchange_google_code(db, code=code, state=state)
    return {"message": "Google Calendar connected successfully."}


@router.post("/sync/day", response_model=GoogleSyncResponse)
def sync_day_endpoint(
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GoogleSyncResponse:
    return sync_day_to_google(db, current_user, target_date)

