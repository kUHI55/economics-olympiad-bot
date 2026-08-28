import unittest
from datetime import UTC, datetime

from app.core.enums import AttemptVerdict
from app.services.review.policy import ReviewPolicy, ReviewState


class ReviewPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ReviewPolicy()
        self.now = datetime(2026, 8, 28, 12, tzinfo=UTC)

    def test_success_intervals_progress_from_three_to_seven_days(self) -> None:
        first = self.policy.advance(ReviewState(), AttemptVerdict.CORRECT, self.now)
        second = self.policy.advance(first.state, AttemptVerdict.CORRECT, self.now)
        self.assertEqual(first.state.interval_days, 3)
        self.assertEqual(second.state.interval_days, 7)

    def test_failure_resets_success_and_is_due_tomorrow(self) -> None:
        decision = self.policy.advance(
            ReviewState(success_count=3, interval_days=14), AttemptVerdict.INCORRECT, self.now
        )
        self.assertEqual(decision.state.success_count, 0)
        self.assertEqual(decision.state.interval_days, 1)
        self.assertEqual((decision.next_review - self.now).days, 1)
