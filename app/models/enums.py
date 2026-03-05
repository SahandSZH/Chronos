from enum import Enum


class RepeatType(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"


class ExternalProvider(str, Enum):
    GOOGLE = "google"

