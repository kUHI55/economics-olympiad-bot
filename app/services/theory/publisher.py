from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.content import (
    KnowledgeElement,
    MaterialDraft,
    Question,
    QuestionOption,
    Source,
)
from app.database.models.learning import ReviewSchedule
from app.schemas.analysis import MaterialAnalysis


class SourcePublisher:
    """Turns an administrator-approved draft into source-linked database records in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish(self, draft: MaterialDraft, analysis: MaterialAnalysis) -> Source:
        if not analysis.knowledge_elements:
            raise ValueError("Нельзя сохранить пустой набор знаний.")
        source = Source(
            created_by_id=draft.created_by_id,
            section_id=draft.section_id,
            topic_id=draft.topic_id,
            subtopic_id=draft.subtopic_id,
            source_name=draft.source_name,
            source_type=draft.source_type,
            source_date=draft.source_date,
            content=draft.content,
            file_path=draft.file_path,
        )
        self.session.add(source)
        await self.session.flush()

        elements: list[KnowledgeElement] = []
        for item in analysis.knowledge_elements:
            element = KnowledgeElement(
                source_id=source.id,
                section_id=draft.section_id,
                topic_id=draft.topic_id,
                subtopic_id=draft.subtopic_id,
                title=item.title,
                knowledge_type=item.knowledge_type,
                content=item.content,
                formula=item.formula,
                notation=item.notation,
                economic_meaning=item.economic_meaning,
                source_excerpt=item.source_excerpt,
            )
            elements.append(element)
            self.session.add(element)
        await self.session.flush()

        # New material is due immediately for its owner, while other users get a schedule on first attempt.
        now = datetime.now(UTC)
        self.session.add_all(
            [
                ReviewSchedule(
                    user_id=draft.created_by_id,
                    knowledge_element_id=element.id,
                    next_review=now,
                )
                for element in elements
            ]
        )

        for item in analysis.questions:
            question = Question(
                knowledge_element_id=elements[item.knowledge_element_index].id,
                source_id=source.id,
                question=item.question,
                question_type=item.question_type,
                difficulty=item.difficulty,
                reference_answer=item.reference_answer,
                key_points=item.key_points,
                hint=item.hint,
                explanation=item.explanation,
                source_excerpt=item.source_excerpt,
            )
            self.session.add(question)
            await self.session.flush()
            self.session.add_all(
                [
                    QuestionOption(
                        question_id=question.id,
                        position=position,
                        option_text=option.text,
                        is_correct=option.is_correct,
                    )
                    for position, option in enumerate(item.options, start=1)
                ]
            )
        await self.session.delete(draft)
        return source
