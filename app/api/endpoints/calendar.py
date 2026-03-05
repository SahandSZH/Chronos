from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import CalendarMonthResponse, TaskDayResponse
from app.services.task_service import calendar_month_summary, get_user_today, list_tasks_for_day

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/month", response_model=CalendarMonthResponse)
def month_view(
    year: int | None = Query(default=None, ge=1900, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarMonthResponse:
    today = get_user_today(current_user)
    use_year = year or today.year
    use_month = month or today.month
    return calendar_month_summary(db, current_user, use_year, use_month)


@router.get("/day/{target_date}", response_model=TaskDayResponse)
def day_view(
    target_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDayResponse:
    return TaskDayResponse(date=target_date, tasks=list_tasks_for_day(db, current_user, target_date))

