import random
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AttemptVerdict, QuestionType, QuizMode
from app.database.models.content import KnowledgeElement, Question
from app.database.models.learning import Attempt, QuizSession, SessionQuestion


class QuizService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        user_id: int,
        mode: QuizMode,
        scope_type: str = "all",
        scope_id: int | None = None,
        question_types: set[QuestionType] | None = None,
        question_count: int = 20,
        only_knowledge_element_ids: list[int] | None = None,
        only_question_ids: list[int] | None = None,
    ) -> QuizSession:
        query = select(Question).join(KnowledgeElement).where(Question.is_active.is_(True))
        if scope_type == "section" and scope_id:
            query = query.where(KnowledgeElement.section_id == scope_id)
        elif scope_type == "topic" and scope_id:
            query = query.where(KnowledgeElement.topic_id == scope_id)
        elif scope_type == "subtopic" and scope_id:
            query = query.where(KnowledgeElement.subtopic_id == scope_id)
        if question_types:
            query = query.where(Question.question_type.in_(question_types))
        if only_knowledge_element_ids is not None:
            query = query.where(Question.knowledge_element_id.in_(only_knowledge_element_ids))
        if only_question_ids is not None:
            query = query.where(Question.id.in_(only_question_ids))
        candidates = list(await self.session.scalars(query))
        selected = self._select_questions(candidates, mode, question_types, question_count)
        session = QuizSession(
            user_id=user_id,
            mode=mode,
            scope_type=scope_type,
            scope_id=scope_id,
            total_questions=len(selected),
        )
        self.session.add(session)
        await self.session.flush()
        self.session.add_all(
            [
                SessionQuestion(
                    quiz_session_id=session.id, question_id=question.id, position=position
                )
                for position, question in enumerate(selected, start=1)
            ]
        )
        return session

    @staticmethod
    def _select_questions(
        candidates: list[Question],
        mode: QuizMode,
        question_types: set[QuestionType] | None,
        question_count: int,
    ) -> list[Question]:
        random.shuffle(candidates)
        # The normal "mixed" mode follows the requested 20-question distribution where possible.
        if mode is not QuizMode.PRACTICE or question_types is not None or question_count != 20:
            return candidates[:question_count]
        quotas = {
            QuestionType.FORMULA: 4,
            QuestionType.DEFINITION: 4,
            QuestionType.UNDERSTANDING: 6,
            QuestionType.CAUSAL_RELATIONSHIP: 3,
            QuestionType.MULTIPLE_CHOICE: 3,
        }
        selected: list[Question] = []
        selected_ids: set[int] = set()
        for question_type, quota in quotas.items():
            group = [item for item in candidates if item.question_type is question_type]
            for item in group[:quota]:
                selected.append(item)
                selected_ids.add(item.id)
        selected.extend(item for item in candidates if item.id not in selected_ids)
        return selected[:question_count]

    async def question_at(self, quiz_session_id: int, position: int) -> Question | None:
        query = (
            select(Question)
            .options(selectinload(Question.options))
            .join(SessionQuestion, SessionQuestion.question_id == Question.id)
            .where(
                SessionQuestion.quiz_session_id == quiz_session_id,
                SessionQuestion.position == position,
            )
        )
        return await self.session.scalar(query)

    async def mark_completed(self, quiz_session_id: int, position: int) -> None:
        item = await self.session.scalar(
            select(SessionQuestion).where(
                SessionQuestion.quiz_session_id == quiz_session_id,
                SessionQuestion.position == position,
            )
        )
        if item:
            item.completed = True

    async def finish(self, quiz_session_id: int) -> tuple[int, int, Counter[QuestionType]]:
        session = await self.session.get(QuizSession, quiz_session_id)
        if session:
            session.completed_at = datetime.now(UTC)
        question_rows = await self.session.execute(
            select(SessionQuestion.question_id, Question.question_type)
            .join(Question, Question.id == SessionQuestion.question_id)
            .where(SessionQuestion.quiz_session_id == quiz_session_id)
        )
        types = dict(question_rows)
        attempts = await self.session.execute(
            select(Attempt.question_id, Attempt.verdict)
            .where(Attempt.quiz_session_id == quiz_session_id)
            .order_by(Attempt.question_id, Attempt.answered_at.desc())
        )
        latest: dict[int, AttemptVerdict] = {}
        for question_id, verdict in attempts:
            latest.setdefault(question_id, verdict)
        correct = sum(verdict is AttemptVerdict.CORRECT for verdict in latest.values())
        totals = Counter(types.values())
        return correct, len(types), totals

    async def error_question_ids(self, quiz_session_id: int) -> list[int]:
        attempts = await self.session.execute(
            select(Attempt.question_id, Attempt.verdict)
            .where(Attempt.quiz_session_id == quiz_session_id)
            .order_by(Attempt.question_id, Attempt.answered_at.desc())
        )
        latest: dict[int, AttemptVerdict] = {}
        for question_id, verdict in attempts:
            latest.setdefault(question_id, verdict)
        return [
            question_id
            for question_id, verdict in latest.items()
            if verdict is not AttemptVerdict.CORRECT
        ]

    async def belongs_to_user(self, quiz_session_id: int, user_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(QuizSession.id).where(
                    QuizSession.id == quiz_session_id,
                    QuizSession.user_id == user_id,
                )
            )
        )

    async def error_question_texts(self, quiz_session_id: int) -> list[str]:
        question_ids = await self.error_question_ids(quiz_session_id)
        if not question_ids:
            return []
        return list(
            await self.session.scalars(
                select(Question.question).where(Question.id.in_(question_ids)).order_by(Question.id)
            )
        )
