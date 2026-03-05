import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import RepeatType, Task, TaskCompletion, User
from app.schemas.task import (
    CalendarDaySummary,
    CalendarMonthResponse,
    ForgottenTask,
    TaskCreate,
    TaskDetail,
    TaskSummary,
    TaskUpdate,
)


def get_user_today(user: User) -> date:
    settings = get_settings()
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo(settings.default_timezone)
    return datetime.now(tz).date()


def task_occurs_on(task: Task, target_date: date) -> bool:
    if target_date < task.start_date:
        return False
    if task.end_date and target_date > task.end_date:
        return False

    if task.repeat_type == RepeatType.NONE:
        return target_date == task.start_date

    days_delta = (target_date - task.start_date).days

    if task.repeat_type == RepeatType.DAILY:
        return days_delta % task.repeat_interval == 0

    if task.repeat_type == RepeatType.WEEKLY:
        weekdays = task.repeat_weekdays or []
        if target_date.weekday() not in weekdays:
            return False
        weeks_delta = days_delta // 7
        return weeks_delta % task.repeat_interval == 0

    return False


def validate_task_schedule(
    repeat_type: RepeatType,
    start_date: date,
    end_date: date | None,
    repeat_interval: int,
    repeat_weekdays: list[int] | None,
) -> None:
    if end_date and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be on or after start_date.",
        )

    if repeat_interval < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repeat_interval must be at least 1.",
        )

    if repeat_type == RepeatType.WEEKLY and not repeat_weekdays:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repeat_weekdays is required for weekly tasks.",
        )


def _completion_set(
    db: Session, user_id, task_ids: list, start_date: date, end_date: date
) -> set[tuple]:
    if not task_ids:
        return set()

    rows = db.execute(
        select(TaskCompletion.task_id, TaskCompletion.occurrence_date).where(
            TaskCompletion.user_id == user_id,
            TaskCompletion.task_id.in_(task_ids),
            TaskCompletion.occurrence_date >= start_date,
            TaskCompletion.occurrence_date <= end_date,
        )
    ).all()
    return {(row.task_id, row.occurrence_date) for row in rows}


def create_task(db: Session, user: User, payload: TaskCreate) -> Task:
    validate_task_schedule(
        repeat_type=payload.repeat_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        repeat_interval=payload.repeat_interval,
        repeat_weekdays=payload.repeat_weekdays,
    )

    task = Task(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        related_link=payload.related_link,
        start_date=payload.start_date,
        end_date=payload.end_date,
        repeat_type=payload.repeat_type,
        repeat_interval=payload.repeat_interval if payload.repeat_type != RepeatType.NONE else 1,
        repeat_weekdays=payload.repeat_weekdays if payload.repeat_type == RepeatType.WEEKLY else None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task_or_404(db: Session, user: User, task_id) -> Task:
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user.id)
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


def update_task(db: Session, user: User, task_id, payload: TaskUpdate) -> Task:
    task = get_task_or_404(db, user, task_id)
    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(task, field, value)

    if task.repeat_type != RepeatType.WEEKLY:
        task.repeat_weekdays = None
    if task.repeat_type == RepeatType.NONE:
        task.repeat_interval = 1

    validate_task_schedule(
        repeat_type=task.repeat_type,
        start_date=task.start_date,
        end_date=task.end_date,
        repeat_interval=task.repeat_interval,
        repeat_weekdays=task.repeat_weekdays,
    )

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user: User, task_id) -> None:
    task = get_task_or_404(db, user, task_id)
    db.delete(task)
    db.commit()


def list_tasks_for_day(db: Session, user: User, target_date: date) -> list[TaskSummary]:
    tasks = db.execute(
        select(Task).where(
            Task.user_id == user.id,
            or_(
                and_(Task.repeat_type == RepeatType.NONE, Task.start_date == target_date),
                and_(
                    Task.repeat_type != RepeatType.NONE,
                    Task.start_date <= target_date,
                    or_(Task.end_date.is_(None), Task.end_date >= target_date),
                ),
            ),
        )
    ).scalars().all()

    task_ids = [task.id for task in tasks if task_occurs_on(task, target_date)]
    completed = _completion_set(db, user.id, task_ids, target_date, target_date)

    visible_tasks = [
        TaskSummary(
            id=task.id,
            title=task.title,
            occurrence_date=target_date,
            is_completed=(task.id, target_date) in completed,
            related_link=task.related_link,
            repeat_type=task.repeat_type,
        )
        for task in tasks
        if task_occurs_on(task, target_date)
    ]

    visible_tasks.sort(key=lambda item: (item.is_completed, item.title.lower()))
    return visible_tasks


def get_task_detail(db: Session, user: User, task_id, target_date: date | None) -> TaskDetail:
    task = get_task_or_404(db, user, task_id)
    date_for_status = target_date or get_user_today(user)

    completion = db.execute(
        select(TaskCompletion).where(
            TaskCompletion.task_id == task.id,
            TaskCompletion.occurrence_date == date_for_status,
        )
    ).scalar_one_or_none()

    detail = TaskDetail.model_validate(task)
    detail.completed_for_date = completion is not None
    detail.completion_date = date_for_status if completion else None
    return detail


def set_task_completion(
    db: Session, user: User, task_id, target_date: date | None, done: bool
) -> TaskDetail:
    task = get_task_or_404(db, user, task_id)
    occurrence_date = target_date or get_user_today(user)

    if not task_occurs_on(task, occurrence_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task does not occur on the selected date.",
        )

    existing = db.execute(
        select(TaskCompletion).where(
            TaskCompletion.task_id == task.id,
            TaskCompletion.occurrence_date == occurrence_date,
        )
    ).scalar_one_or_none()

    if done and not existing:
        db.add(
            TaskCompletion(task_id=task.id, user_id=user.id, occurrence_date=occurrence_date)
        )
        db.commit()
    elif not done and existing:
        db.delete(existing)
        db.commit()

    db.refresh(task)
    return get_task_detail(db, user, task.id, occurrence_date)


def list_forgotten_tasks(
    db: Session, user: User, until_date: date | None = None, lookback_days: int = 180
) -> list[ForgottenTask]:
    today = get_user_today(user)
    until = until_date or (today - timedelta(days=1))
    if until < date.min:
        return []

    since = until - timedelta(days=lookback_days)

    tasks = db.execute(
        select(Task).where(Task.user_id == user.id, Task.start_date <= until)
    ).scalars().all()

    if not tasks:
        return []

    completion_rows = db.execute(
        select(TaskCompletion.task_id, TaskCompletion.occurrence_date).where(
            TaskCompletion.user_id == user.id,
            TaskCompletion.occurrence_date >= since,
            TaskCompletion.occurrence_date <= until,
        )
    ).all()
    completed = {(row.task_id, row.occurrence_date) for row in completion_rows}

    forgotten: list[ForgottenTask] = []

    for task in tasks:
        if task.repeat_type == RepeatType.NONE:
            occurrence = task.start_date
            if since <= occurrence <= until and (task.id, occurrence) not in completed:
                forgotten.append(
                    ForgottenTask(
                        id=task.id,
                        title=task.title,
                        occurrence_date=occurrence,
                        overdue_days=max((today - occurrence).days, 0),
                        related_link=task.related_link,
                        repeat_type=task.repeat_type,
                    )
                )
            continue

        window_start = max(task.start_date, since)
        window_end = min(task.end_date or until, until)

        cursor = window_start
        while cursor <= window_end:
            if task_occurs_on(task, cursor) and (task.id, cursor) not in completed:
                forgotten.append(
                    ForgottenTask(
                        id=task.id,
                        title=task.title,
                        occurrence_date=cursor,
                        overdue_days=max((today - cursor).days, 0),
                        related_link=task.related_link,
                        repeat_type=task.repeat_type,
                    )
                )
            cursor += timedelta(days=1)

    forgotten.sort(key=lambda item: (item.occurrence_date, item.title.lower()))
    return forgotten


def calendar_month_summary(db: Session, user: User, year: int, month: int) -> CalendarMonthResponse:
    settings = get_settings()
    _, total_days = calendar.monthrange(year, month)
    rows: list[CalendarDaySummary] = []

    for day in range(1, total_days + 1):
        target = date(year, month, day)
        tasks = list_tasks_for_day(db, user, target)
        completed_tasks = sum(1 for task in tasks if task.is_completed)
        total_tasks = len(tasks)
        rows.append(
            CalendarDaySummary(
                date=target,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                pending_tasks=total_tasks - completed_tasks,
            )
        )

    return CalendarMonthResponse(year=year, month=month, locale=user.locale or settings.calendar_locale, days=rows)

