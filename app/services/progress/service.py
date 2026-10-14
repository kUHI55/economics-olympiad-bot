from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AttemptVerdict
from app.database.models.content import Question
from app.database.models.learning import Attempt, Progress, ReviewSchedule
from app.services.review.policy import ReviewPolicy, ReviewState


class ProgressService:
    def __init__(self, session: AsyncSession, review_policy: ReviewPolicy | None = None) -> None:
        self.session = session
        self.review_policy = review_policy or ReviewPolicy()

    async def record_attempt(
        self,
        *,
        user_id: int,
        question: Question,
        answer: str,
        verdict: AttemptVerdict,
        score: float,
        feedback: dict | None,
        hint_used: bool,
        answer_revealed: bool,
        quiz_session_id: int | None = None,
    ) -> Attempt:
        attempt = Attempt(
            user_id=user_id,
            question_id=question.id,
            quiz_session_id=quiz_session_id,
            answer=answer,
            verdict=verdict,
            score=score,
            feedback=feedback,
            hint_used=hint_used,
            answer_revealed=answer_revealed,
        )
        self.session.add(attempt)
        now = datetime.now(UTC)
        progress = await self.session.scalar(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.knowledge_element_id == question.knowledge_element_id,
            )
        )
        if progress is None:
            progress = Progress(
                user_id=user_id,
                knowledge_element_id=question.knowledge_element_id,
                attempts_count=0,
                correct_count=0,
                partial_count=0,
                incorrect_count=0,
                mastery_score=0.0,
            )
            self.session.add(progress)
        progress.attempts_count += 1
        if verdict is AttemptVerdict.CORRECT:
            progress.correct_count += 1
        elif verdict is AttemptVerdict.PARTIAL:
            progress.partial_count += 1
        else:
            progress.incorrect_count += 1
        progress.mastery_score = (
            progress.correct_count + progress.partial_count * 0.5
        ) / progress.attempts_count
        progress.last_attempt_at = now

        schedule = await self.session.scalar(
            select(ReviewSchedule).where(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.knowledge_element_id == question.knowledge_element_id,
            )
        )
        if schedule is None:
            schedule = ReviewSchedule(
                user_id=user_id,
                knowledge_element_id=question.knowledge_element_id,
                next_review=now,
                success_count=0,
                failure_count=0,
                interval_days=0,
            )
            self.session.add(schedule)
        decision = self.review_policy.advance(
            ReviewState(schedule.success_count, schedule.failure_count, schedule.interval_days),
            verdict,
            now,
        )
        schedule.success_count = decision.state.success_count
        schedule.failure_count = decision.state.failure_count
        schedule.interval_days = decision.state.interval_days
        schedule.last_review = now
        schedule.next_review = decision.next_review
        return attempt

    async def mark_answer_revealed(
        self, *, user_id: int, question_id: int, quiz_session_id: int
    ) -> None:
        attempt = await self.session.scalar(
            select(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.question_id == question_id,
                Attempt.quiz_session_id == quiz_session_id,
            )
            .order_by(Attempt.answered_at.desc())
            .limit(1)
        )
        if attempt:
            attempt.answer_revealed = True
