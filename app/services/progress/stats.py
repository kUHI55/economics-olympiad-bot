from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AttemptVerdict, QuestionType
from app.database.models.catalog import Topic
from app.database.models.content import KnowledgeElement, Question
from app.database.models.learning import Attempt, Progress


@dataclass(frozen=True)
class TopicMastery:
    topic_name: str
    score: float


@dataclass(frozen=True)
class QuestionTypeMastery:
    question_type: QuestionType
    correct: int
    total: int

    @property
    def score(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass(frozen=True)
class ProgressSummary:
    total_elements: int
    reviewed_elements: int
    attempts: int
    correct: int
    incorrect: int
    topics: list[TopicMastery]
    question_types: list[QuestionTypeMastery]


class StatisticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self, user_id: int) -> ProgressSummary:
        total_elements = await self.session.scalar(select(func.count(KnowledgeElement.id))) or 0
        totals = (
            await self.session.execute(
                select(
                    func.count(Progress.id),
                    func.coalesce(func.sum(Progress.attempts_count), 0),
                    func.coalesce(func.sum(Progress.correct_count), 0),
                    func.coalesce(func.sum(Progress.incorrect_count), 0),
                ).where(Progress.user_id == user_id)
            )
        ).one()
        topic_rows = await self.session.execute(
            select(Topic.name, func.avg(Progress.mastery_score))
            .join(KnowledgeElement, KnowledgeElement.topic_id == Topic.id)
            .join(
                Progress,
                (Progress.knowledge_element_id == KnowledgeElement.id)
                & (Progress.user_id == user_id),
            )
            .group_by(Topic.id, Topic.name)
            .order_by(func.avg(Progress.mastery_score))
        )
        type_rows = await self.session.execute(
            select(
                Question.question_type,
                func.count(Attempt.id),
                func.coalesce(
                    func.sum(case((Attempt.verdict == AttemptVerdict.CORRECT, 1), else_=0)), 0
                ),
            )
            .join(Question, Question.id == Attempt.question_id)
            .where(Attempt.user_id == user_id)
            .group_by(Question.question_type)
            .order_by(Question.question_type)
        )
        return ProgressSummary(
            total_elements=total_elements,
            reviewed_elements=totals[0],
            attempts=totals[1],
            correct=totals[2],
            incorrect=totals[3],
            topics=[TopicMastery(name, float(score)) for name, score in topic_rows],
            question_types=[
                QuestionTypeMastery(question_type, int(correct), int(total))
                for question_type, total, correct in type_rows
            ],
        )
