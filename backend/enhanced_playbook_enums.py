from enum import Enum


class StepStatus(Enum):
    PENDING          = "pending"
    RUNNING          = "running"
    COMPLETED        = "completed"
    FAILED           = "failed"
    SKIPPED          = "skipped"
    WAITING_APPROVAL = "waiting_approval"
