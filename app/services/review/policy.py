from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.enums import AttemptVerdict


@dataclass(frozen=True)
class ReviewState:
    success_count: int = 0
    failure_count: int = 0
    interval_days: int = 0


@dataclass(frozen=True)
class ReviewDecision:
    state: ReviewState
    next_review: datetime


class ReviewPolicy:
    """Deliberately small, transparent spaced-repetition algorithm for the MVP."""

    success_intervals = (3, 7, 14, 30)

    def advance(
        self, state: ReviewState, verdict: AttemptVerdict, now: datetime | None = None
    ) -> ReviewDecision:
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            raise ValueError("Review timestamps must be timezone-aware")
        if verdict is AttemptVerdict.CORRECT:
            successes = state.success_count + 1
            interval = self.success_intervals[min(successes - 1, len(self.success_intervals) - 1)]
            next_state = ReviewState(successes, state.failure_count, interval)
        elif verdict is AttemptVerdict.PARTIAL:
            next_state = ReviewState(state.success_count, state.failure_count + 1, 1)
        else:
            next_state = ReviewState(0, state.failure_count + 1, 1)
        return ReviewDecision(next_state, current_time + timedelta(days=next_state.interval_days))
