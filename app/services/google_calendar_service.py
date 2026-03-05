from datetime import date, timedelta

from fastapi import HTTPException, status
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_google_oauth_state, verify_google_oauth_state
from app.models import ExternalEvent, ExternalProvider, GoogleToken, Task, User
from app.schemas.google import GoogleConnectionStatus, GoogleSyncResponse
from app.services.task_service import list_tasks_for_day


def _assert_google_oauth_config() -> None:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
            ),
        )


def _build_flow(state: str | None = None) -> Flow:
    settings = get_settings()
    _assert_google_oauth_config()

    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config=client_config,
        scopes=settings.google_scopes,
        state=state,
        redirect_uri=settings.google_redirect_uri,
    )


def build_google_auth_url(user: User) -> tuple[str, str]:
    state = create_google_oauth_state(str(user.id))
    flow = _build_flow(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def _upsert_google_token(db: Session, user: User, credentials: Credentials) -> GoogleToken:
    token = db.execute(select(GoogleToken).where(GoogleToken.user_id == user.id)).scalar_one_or_none()

    if token is None:
        token = GoogleToken(user_id=user.id)
        db.add(token)

    token.access_token = credentials.token
    token.refresh_token = credentials.refresh_token or token.refresh_token
    token.token_uri = credentials.token_uri or "https://oauth2.googleapis.com/token"
    token.scopes = list(credentials.scopes or [])
    token.expiry = credentials.expiry

    db.commit()
    db.refresh(token)
    return token


def exchange_google_code(db: Session, code: str, state: str) -> GoogleToken:
    try:
        user_id = verify_google_oauth_state(state)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state."
        ) from exc
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    flow = _build_flow(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to exchange authorization code with Google.",
        ) from exc

    return _upsert_google_token(db, user, flow.credentials)


def google_connection_status(db: Session, user: User) -> GoogleConnectionStatus:
    token = db.execute(select(GoogleToken).where(GoogleToken.user_id == user.id)).scalar_one_or_none()
    if token is None:
        return GoogleConnectionStatus(connected=False)
    return GoogleConnectionStatus(connected=True, expiry=token.expiry, scopes=token.scopes or [])


def _google_credentials_or_400(db: Session, user: User) -> Credentials:
    settings = get_settings()
    _assert_google_oauth_config()

    token = db.execute(select(GoogleToken).where(GoogleToken.user_id == user.id)).scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected for this user.",
        )

    credentials = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri=token.token_uri,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=token.scopes,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _upsert_google_token(db, user, credentials)
    elif credentials.expired and not credentials.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token expired. Reconnect your Google account.",
        )

    return credentials


def _event_payload(task: Task, target_date: date, is_completed: bool) -> dict:
    status_prefix = "Done: " if is_completed else ""
    lines = []
    if task.description:
        lines.append(task.description)
    if task.related_link:
        lines.append(f"Related link: {task.related_link}")
    lines.append(f"Task status: {'completed' if is_completed else 'pending'}")

    return {
        "summary": f"{status_prefix}{task.title}",
        "description": "\n\n".join(lines),
        "start": {"date": target_date.isoformat()},
        "end": {"date": (target_date + timedelta(days=1)).isoformat()},
    }


def sync_day_to_google(db: Session, user: User, target_date: date) -> GoogleSyncResponse:
    credentials = _google_credentials_or_400(db, user)
    day_tasks = list_tasks_for_day(db, user, target_date)

    if not day_tasks:
        return GoogleSyncResponse(
            date=target_date,
            total_tasks=0,
            created_events=0,
            updated_events=0,
            skipped_tasks=0,
        )

    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    task_ids = [task.id for task in day_tasks]

    task_models = db.execute(select(Task).where(Task.user_id == user.id, Task.id.in_(task_ids))).scalars().all()
    task_map = {task.id: task for task in task_models}

    mappings = db.execute(
        select(ExternalEvent).where(
            ExternalEvent.user_id == user.id,
            ExternalEvent.provider == ExternalProvider.GOOGLE,
            ExternalEvent.occurrence_date == target_date,
            ExternalEvent.task_id.in_(task_ids),
        )
    ).scalars().all()
    map_by_task = {mapping.task_id: mapping for mapping in mappings}

    created = 0
    updated = 0
    skipped = 0

    for task_item in day_tasks:
        task_model = task_map.get(task_item.id)
        if task_model is None:
            skipped += 1
            continue

        event_body = _event_payload(task_model, target_date, task_item.is_completed)
        mapping = map_by_task.get(task_item.id)

        try:
            if mapping:
                service.events().update(
                    calendarId="primary", eventId=mapping.external_event_id, body=event_body
                ).execute()
                updated += 1
            else:
                event = service.events().insert(calendarId="primary", body=event_body).execute()
                db.add(
                    ExternalEvent(
                        user_id=user.id,
                        task_id=task_item.id,
                        occurrence_date=target_date,
                        provider=ExternalProvider.GOOGLE,
                        external_event_id=event["id"],
                    )
                )
                created += 1
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if mapping and status_code == 404:
                event = service.events().insert(calendarId="primary", body=event_body).execute()
                mapping.external_event_id = event["id"]
                created += 1
                continue
            skipped += 1

    db.commit()
    return GoogleSyncResponse(
        date=target_date,
        total_tasks=len(day_tasks),
        created_events=created,
        updated_events=updated,
        skipped_tasks=skipped,
    )
