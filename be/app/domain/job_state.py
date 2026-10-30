"""The single place that defines which job status changes are allowed."""

from app.core.exceptions import InvalidStateError
from app.models.work import JobStatus

S = JobStatus

TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    S.UNASSIGNED: frozenset({S.ASSIGNED, S.IN_PROGRESS}),
    S.ASSIGNED: frozenset({S.IN_PROGRESS, S.UNASSIGNED, S.ASSIGNED}),
    S.IN_PROGRESS: frozenset({S.SUBMITTED, S.UNASSIGNED, S.ASSIGNED}),
    # SUBMITTED -> ACCEPTED is review sampling: a job that is not picked for review.
    S.SUBMITTED: frozenset({S.IN_REVIEW, S.ACCEPTED}),
    S.IN_REVIEW: frozenset({S.ACCEPTED, S.ACCEPTED_WITH_FIX, S.REJECTED, S.ESCALATED, S.SUBMITTED}),
    S.REJECTED: frozenset({S.IN_PROGRESS, S.UNASSIGNED, S.ASSIGNED, S.ACCEPTED}),
    S.ESCALATED: frozenset({S.ACCEPTED, S.REJECTED}),
    # Re-review sends an accepted job back to the review queue.
    # An owner override can also flip an accepted job back to rejected.
    S.ACCEPTED: frozenset({S.SUBMITTED, S.REJECTED}),
    S.ACCEPTED_WITH_FIX: frozenset({S.SUBMITTED, S.REJECTED, S.ACCEPTED}),
}


def ensure_transition(current: str, target: JobStatus) -> None:
    allowed = TRANSITIONS.get(JobStatus(current), frozenset())
    if target not in allowed:
        raise InvalidStateError(
            f"Job cannot go from {current} to {target}",
            details={"from": current, "to": target, "allowed": sorted(allowed)},
        )
