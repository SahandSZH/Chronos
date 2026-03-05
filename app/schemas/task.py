from datetime import date as dt_date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import RepeatType


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    related_link: str | None = Field(default=None, max_length=2048)
    start_date: dt_date
    end_date: dt_date | None = None
    repeat_type: RepeatType = RepeatType.NONE
    repeat_interval: int = Field(default=1, ge=1, le=365)
    repeat_weekdays: list[int] | None = None

    @field_validator("repeat_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        normalized = sorted(set(value))
        if not all(0 <= day <= 6 for day in normalized):
            raise ValueError("repeat_weekdays must contain values from 0 (Mon) to 6 (Sun).")
        return normalized


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    related_link: str | None = Field(default=None, max_length=2048)
    start_date: dt_date | None = None
    end_date: dt_date | None = None
    repeat_type: RepeatType | None = None
    repeat_interval: int | None = Field(default=None, ge=1, le=365)
    repeat_weekdays: list[int] | None = None

    @field_validator("repeat_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        normalized = sorted(set(value))
        if not all(0 <= day <= 6 for day in normalized):
            raise ValueError("repeat_weekdays must contain values from 0 (Mon) to 6 (Sun).")
        return normalized


class TaskSummary(BaseModel):
    id: UUID
    title: str
    occurrence_date: dt_date
    is_completed: bool
    related_link: str | None
    repeat_type: RepeatType


class TaskDetail(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    completed_for_date: bool = False
    completion_date: dt_date | None = None


class TaskDayResponse(BaseModel):
    date: dt_date
    tasks: list[TaskSummary]


class ForgottenTask(BaseModel):
    id: UUID
    title: str
    occurrence_date: dt_date
    overdue_days: int
    related_link: str | None
    repeat_type: RepeatType


class ForgottenResponse(BaseModel):
    tasks: list[ForgottenTask]


class TaskCompletionUpdate(BaseModel):
    done: bool = True
    date: dt_date | None = None


class CalendarDaySummary(BaseModel):
    date: dt_date
    total_tasks: int
    completed_tasks: int
    pending_tasks: int


class CalendarMonthResponse(BaseModel):
    year: int
    month: int
    locale: str
    days: list[CalendarDaySummary]
