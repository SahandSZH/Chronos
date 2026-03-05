from datetime import date, datetime

from pydantic import BaseModel


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class GoogleConnectionStatus(BaseModel):
    connected: bool
    expiry: datetime | None = None
    scopes: list[str] = []


class GoogleSyncResponse(BaseModel):
    date: date
    total_tasks: int
    created_events: int
    updated_events: int
    skipped_tasks: int

