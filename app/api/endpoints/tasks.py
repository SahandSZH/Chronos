from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    ForgottenResponse,
    TaskCompletionUpdate,
    TaskCreate,
    TaskDayResponse,
    TaskDetail,
    TaskUpdate,
)
from app.services.task_service import (
    create_task,
    delete_task,
    get_task_detail,
    get_user_today,
    list_forgotten_tasks,
    list_tasks_for_day,
    set_task_completion,
    update_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/today", response_model=TaskDayResponse)
def today_tasks(
    date_override: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDayResponse:
    target = date_override or get_user_today(current_user)
    return TaskDayResponse(date=target, tasks=list_tasks_for_day(db, current_user, target))


@router.get("/day/{target_date}", response_model=TaskDayResponse)
def tasks_for_day(
    target_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDayResponse:
    return TaskDayResponse(date=target_date, tasks=list_tasks_for_day(db, current_user, target_date))


@router.get("/forgotten", response_model=ForgottenResponse)
def forgotten_tasks(
    until_date: date | None = Query(default=None),
    lookback_days: int = Query(default=180, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ForgottenResponse:
    items = list_forgotten_tasks(
        db=db, user=current_user, until_date=until_date, lookback_days=lookback_days
    )
    return ForgottenResponse(tasks=items)


@router.post("/", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
def create_new_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    task = create_task(db, current_user, payload)
    return get_task_detail(db, current_user, task.id, task.start_date)


@router.get("/{task_id}", response_model=TaskDetail)
def task_detail(
    task_id: UUID,
    target_date: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    return get_task_detail(db, current_user, task_id, target_date)


@router.patch("/{task_id}", response_model=TaskDetail)
def update_existing_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    task = update_task(db, current_user, task_id, payload)
    return get_task_detail(db, current_user, task.id, task.start_date)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    delete_task(db, current_user, task_id)
    return None


@router.post("/{task_id}/completion", response_model=TaskDetail)
def update_task_completion(
    task_id: UUID,
    payload: TaskCompletionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    return set_task_completion(db, current_user, task_id, payload.date, payload.done)

