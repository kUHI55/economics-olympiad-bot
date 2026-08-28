"""Synchronize versioned theory files with PostgreSQL without rewriting learning history."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.catalog import Section, Subtopic, Topic
from app.database.models.content import KnowledgeElement, Question, QuestionOption, Source
from app.database.models.user import User
from app.theory_data.models import KnowledgeItem, QuestionItem, SourceReference, TaxonomyDocument
from app.theory_data.validator import load_theory_repository

SYSTEM_IMPORTER_TELEGRAM_ID = -1


class TheoryImportError(RuntimeError):
    """A database conflict that prevents a safe GitHub theory synchronization."""


@dataclass(frozen=True)
class TheorySyncReport:
    sections: int
    topics: int
    subtopics: int
    sources: int
    knowledge_elements: int
    questions: int
    deactivated_knowledge_elements: int
    deactivated_questions: int


class TheoryImporter:
    """Apply a fully validated theory repository in one database transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._sources: dict[str, Source] = {}

    async def synchronize(self, root: Path) -> TheorySyncReport:
        """Validate all files first, then upsert them atomically by stable external IDs."""
        repository = load_theory_repository(root)
        self._sources = {}
        seen_knowledge_ids: set[str] = set()
        seen_question_ids: set[str] = set()
        section_ids: set[str] = set()
        topic_ids: set[str] = set()
        subtopic_ids: set[str] = set()
        source_ids: set[str] = set()

        async with self.session.begin():
            knowledge_by_external_id: dict[str, KnowledgeElement] = {}
            for topic_directory in repository.topics:
                taxonomy = topic_directory.knowledge
                section = await self._upsert_section(taxonomy)
                topic = await self._upsert_topic(section, taxonomy)
                subtopic = await self._upsert_subtopic(topic, taxonomy)
                section_ids.add(section.external_id or "")
                topic_ids.add(topic.external_id or "")
                if subtopic is not None:
                    subtopic_ids.add(subtopic.external_id or "")

                relative_path = topic_directory.directory.relative_to(root).as_posix()
                for item in topic_directory.knowledge.knowledge:
                    source = await self._upsert_source(
                        item.source,
                        section=section,
                        topic=topic,
                        subtopic=subtopic,
                        relative_path=relative_path,
                    )
                    source_ids.add(source.external_id or "")
                    element = await self._upsert_knowledge_element(
                        item,
                        source=source,
                        section=section,
                        topic=topic,
                        subtopic=subtopic,
                    )
                    seen_knowledge_ids.add(item.id)
                    knowledge_by_external_id[item.id] = element

                for item in topic_directory.questions.questions:
                    source = await self._upsert_source(
                        item.source,
                        section=section,
                        topic=topic,
                        subtopic=subtopic,
                        relative_path=relative_path,
                    )
                    source_ids.add(source.external_id or "")
                    element = knowledge_by_external_id[item.knowledge_id]
                    await self._upsert_question(item, source=source, knowledge_element=element)
                    seen_question_ids.add(item.id)

            deactivated_elements = await self._deactivate_removed_knowledge(seen_knowledge_ids)
            deactivated_questions = await self._deactivate_removed_questions(seen_question_ids)

        return TheorySyncReport(
            sections=len(section_ids),
            topics=len(topic_ids),
            subtopics=len(subtopic_ids),
            sources=len(source_ids),
            knowledge_elements=repository.report.knowledge_elements,
            questions=repository.report.questions,
            deactivated_knowledge_elements=deactivated_elements,
            deactivated_questions=deactivated_questions,
        )

    async def _upsert_section(self, taxonomy: TaxonomyDocument) -> Section:
        external_id = f"section:{taxonomy.section}"
        section = await self.session.scalar(
            select(Section).where(Section.external_id == external_id)
        )
        if section is None:
            section = await self.session.scalar(
                select(Section).where(Section.name == taxonomy.section_name)
            )
            if section is not None and section.external_id not in (None, external_id):
                raise TheoryImportError(
                    f"Section name {taxonomy.section_name!r} already belongs to {section.external_id!r}"
                )
        if section is None:
            section = Section(external_id=external_id, name=taxonomy.section_name)
            self.session.add(section)
            await self.session.flush()
        else:
            section.external_id = external_id
            if section.name != taxonomy.section_name:
                conflict = await self.session.scalar(
                    select(Section).where(
                        Section.name == taxonomy.section_name,
                        Section.id != section.id,
                    )
                )
                if conflict is not None:
                    raise TheoryImportError(
                        f"Section name {taxonomy.section_name!r} is already in use"
                    )
                section.name = taxonomy.section_name
        return section

    async def _upsert_topic(self, section: Section, taxonomy: TaxonomyDocument) -> Topic:
        external_id = f"section:{taxonomy.section}/topic:{taxonomy.topic}"
        topic = await self.session.scalar(select(Topic).where(Topic.external_id == external_id))
        if topic is None:
            topic = await self.session.scalar(
                select(Topic).where(
                    Topic.section_id == section.id,
                    Topic.name == taxonomy.topic_name,
                )
            )
            if topic is not None and topic.external_id not in (None, external_id):
                raise TheoryImportError(
                    f"Topic name {taxonomy.topic_name!r} already belongs to {topic.external_id!r}"
                )
        if topic is None:
            topic = Topic(
                external_id=external_id,
                section_id=section.id,
                name=taxonomy.topic_name,
            )
            self.session.add(topic)
            await self.session.flush()
        else:
            topic.external_id = external_id
            topic.section_id = section.id
            if topic.name != taxonomy.topic_name:
                conflict = await self.session.scalar(
                    select(Topic).where(
                        Topic.section_id == section.id,
                        Topic.name == taxonomy.topic_name,
                        Topic.id != topic.id,
                    )
                )
                if conflict is not None:
                    raise TheoryImportError(f"Topic name {taxonomy.topic_name!r} is already in use")
                topic.name = taxonomy.topic_name
        return topic

    async def _upsert_subtopic(
        self, topic: Topic, taxonomy: TaxonomyDocument
    ) -> Subtopic | None:
        if taxonomy.subtopic is None:
            return None
        external_id = (
            f"section:{taxonomy.section}/topic:{taxonomy.topic}/subtopic:{taxonomy.subtopic}"
        )
        subtopic = await self.session.scalar(
            select(Subtopic).where(Subtopic.external_id == external_id)
        )
        if subtopic is None:
            subtopic = await self.session.scalar(
                select(Subtopic).where(
                    Subtopic.topic_id == topic.id,
                    Subtopic.name == taxonomy.subtopic_name,
                )
            )
            if subtopic is not None and subtopic.external_id not in (None, external_id):
                raise TheoryImportError(
                    f"Subtopic name {taxonomy.subtopic_name!r} already belongs to "
                    f"{subtopic.external_id!r}"
                )
        if subtopic is None:
            subtopic = Subtopic(
                external_id=external_id,
                topic_id=topic.id,
                name=taxonomy.subtopic_name or taxonomy.subtopic,
            )
            self.session.add(subtopic)
            await self.session.flush()
        else:
            subtopic.external_id = external_id
            subtopic.topic_id = topic.id
            name = taxonomy.subtopic_name or taxonomy.subtopic
            if subtopic.name != name:
                conflict = await self.session.scalar(
                    select(Subtopic).where(
                        Subtopic.topic_id == topic.id,
                        Subtopic.name == name,
                        Subtopic.id != subtopic.id,
                    )
                )
                if conflict is not None:
                    raise TheoryImportError(f"Subtopic name {name!r} is already in use")
                subtopic.name = name
        return subtopic

    async def _importer_user(self) -> User:
        user = await self.session.scalar(
            select(User).where(User.telegram_id == SYSTEM_IMPORTER_TELEGRAM_ID)
        )
        if user is None:
            user = User(
                telegram_id=SYSTEM_IMPORTER_TELEGRAM_ID,
                username="theory-sync",
                display_name="GitHub theory synchronizer",
            )
            self.session.add(user)
            await self.session.flush()
        return user

    async def _upsert_source(
        self,
        reference: SourceReference,
        *,
        section: Section,
        topic: Topic,
        subtopic: Subtopic | None,
        relative_path: str,
    ) -> Source:
        if reference.id in self._sources:
            return self._sources[reference.id]
        source = await self.session.scalar(select(Source).where(Source.external_id == reference.id))
        if source is None:
            user = await self._importer_user()
            source = Source(
                external_id=reference.id,
                created_by_id=user.id,
                section_id=section.id,
                topic_id=topic.id,
                subtopic_id=subtopic.id if subtopic is not None else None,
                source_name=reference.name,
                source_type=reference.source_type,
                source_date=reference.source_date,
                content=reference.excerpt,
                file_path=relative_path,
            )
            self.session.add(source)
            await self.session.flush()
        source.source_name = reference.name
        source.source_type = reference.source_type
        source.source_date = reference.source_date
        source.content = reference.excerpt
        source.file_path = relative_path
        source.section_id = section.id
        source.topic_id = topic.id
        source.subtopic_id = subtopic.id if subtopic is not None else None
        self._sources[reference.id] = source
        return source

    async def _upsert_knowledge_element(
        self,
        item: KnowledgeItem,
        *,
        source: Source,
        section: Section,
        topic: Topic,
        subtopic: Subtopic | None,
    ) -> KnowledgeElement:
        element = await self.session.scalar(
            select(KnowledgeElement).where(KnowledgeElement.external_id == item.id)
        )
        if element is None:
            element = KnowledgeElement(
                external_id=item.id,
                source_id=source.id,
                section_id=section.id,
                topic_id=topic.id,
                subtopic_id=subtopic.id if subtopic is not None else None,
                title=item.title,
                knowledge_type=item.type,
                content=item.explanation,
                formula=item.formula,
                notation=item.definitions,
                economic_meaning=None,
                source_excerpt=item.source.excerpt,
                is_active=True,
            )
            self.session.add(element)
            await self.session.flush()
        element.source_id = source.id
        element.section_id = section.id
        element.topic_id = topic.id
        element.subtopic_id = subtopic.id if subtopic is not None else None
        element.title = item.title
        element.knowledge_type = item.type
        element.content = item.explanation
        element.formula = item.formula
        element.notation = item.definitions
        element.economic_meaning = None
        element.source_excerpt = item.source.excerpt
        element.is_active = True
        return element

    async def _upsert_question(
        self,
        item: QuestionItem,
        *,
        source: Source,
        knowledge_element: KnowledgeElement,
    ) -> Question:
        question = await self.session.scalar(select(Question).where(Question.external_id == item.id))
        if question is None:
            question = Question(
                external_id=item.id,
                knowledge_element_id=knowledge_element.id,
                source_id=source.id,
                question=item.question,
                question_type=item.type,
                difficulty=item.difficulty,
                reference_answer=item.reference_answer,
                key_points=item.key_points,
                hint="",
                explanation=item.explanation,
                source_excerpt=item.source_excerpt,
            )
            self.session.add(question)
            await self.session.flush()
        question.knowledge_element_id = knowledge_element.id
        question.source_id = source.id
        question.question = item.question
        question.question_type = item.type
        question.difficulty = item.difficulty
        question.reference_answer = item.reference_answer
        question.key_points = item.key_points
        question.hint = ""
        question.explanation = item.explanation
        question.source_excerpt = item.source_excerpt
        question.is_active = True
        await self._upsert_question_options(question, item)
        return question

    async def _upsert_question_options(self, question: Question, item: QuestionItem) -> None:
        existing = {
            option.external_id: option
            for option in await self.session.scalars(
                select(QuestionOption).where(QuestionOption.question_id == question.id)
            )
            if option.external_id is not None
        }
        active_option_ids: set[str] = set()
        for position, option in enumerate(item.options, start=1):
            external_id = f"{item.id}:option:{option.id}"
            active_option_ids.add(external_id)
            record = existing.get(external_id)
            if record is None:
                record = QuestionOption(
                    external_id=external_id,
                    question_id=question.id,
                    position=position,
                    option_text=option.text,
                    is_correct=option.id == item.correct_answer,
                )
                self.session.add(record)
            else:
                record.position = position
                record.option_text = option.text
                record.is_correct = option.id == item.correct_answer
        for external_id, option in existing.items():
            if external_id not in active_option_ids:
                await self.session.delete(option)

    async def _deactivate_removed_knowledge(self, seen_external_ids: set[str]) -> int:
        elements = list(
            await self.session.scalars(
                select(KnowledgeElement).where(KnowledgeElement.external_id.is_not(None))
            )
        )
        deactivated = 0
        for element in elements:
            if element.external_id not in seen_external_ids and element.is_active:
                element.is_active = False
                deactivated += 1
        return deactivated

    async def _deactivate_removed_questions(self, seen_external_ids: set[str]) -> int:
        questions = list(
            await self.session.scalars(select(Question).where(Question.external_id.is_not(None)))
        )
        deactivated = 0
        for question in questions:
            if question.external_id not in seen_external_ids and question.is_active:
                question.is_active = False
                deactivated += 1
        return deactivated
