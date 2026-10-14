import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database.models  # noqa: F401
from app.core.enums import AttemptVerdict
from app.database.base import Base
from app.database.models.content import KnowledgeElement, Question, Source
from app.database.models.learning import Attempt, Progress
from app.database.models.user import User
from app.services.theory.importer import TheoryImporter
from app.theory_data.validator import TheoryValidationError
from tests.theory_fixtures import KNOWLEDGE_ID, QUESTION_ID, write_theory_fixture


class TheoryImporterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.theory_root = Path(self.temporary_directory.name) / "theory"
        self.fixture_directory = self.theory_root / "test-fixture" / "validation-fixture"
        write_theory_fixture(self.fixture_directory)

        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temporary_directory.cleanup()

    async def synchronize(self):
        async with self.session_factory() as session:
            return await TheoryImporter(session).synchronize(self.theory_root)

    async def get_element(self) -> KnowledgeElement:
        async with self.session_factory() as session:
            element = await session.scalar(
                select(KnowledgeElement).where(KnowledgeElement.external_id == KNOWLEDGE_ID)
            )
            self.assertIsNotNone(element)
            return element

    async def test_creates_new_element(self) -> None:
        report = await self.synchronize()
        element = await self.get_element()

        self.assertEqual(report.knowledge_elements, 1)
        self.assertEqual(report.questions, 1)
        self.assertTrue(element.is_active)
        self.assertEqual(element.external_id, KNOWLEDGE_ID)

    async def test_updates_existing_element(self) -> None:
        await self.synchronize()
        knowledge_path = self.fixture_directory / "knowledge.json"
        payload = json.loads(knowledge_path.read_text(encoding="utf-8"))
        payload["knowledge"][0]["title"] = "Updated fixture title"
        knowledge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        await self.synchronize()
        element = await self.get_element()

        self.assertEqual(element.title, "Updated fixture title")

    async def test_preserves_postgresql_id_on_update(self) -> None:
        await self.synchronize()
        original_id = (await self.get_element()).id
        knowledge_path = self.fixture_directory / "knowledge.json"
        payload = json.loads(knowledge_path.read_text(encoding="utf-8"))
        payload["knowledge"][0]["explanation"] = "Updated fixture explanation."
        knowledge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        await self.synchronize()
        self.assertEqual((await self.get_element()).id, original_id)

    async def test_repeated_import_does_not_create_duplicates(self) -> None:
        await self.synchronize()
        await self.synchronize()

        async with self.session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count(Source.id))), 1)
            self.assertEqual(await session.scalar(select(func.count(KnowledgeElement.id))), 1)
            self.assertEqual(await session.scalar(select(func.count(Question.id))), 1)

    async def test_question_is_linked_to_its_knowledge_element(self) -> None:
        await self.synchronize()
        async with self.session_factory() as session:
            element = await session.scalar(
                select(KnowledgeElement).where(KnowledgeElement.external_id == KNOWLEDGE_ID)
            )
            question = await session.scalar(select(Question).where(Question.external_id == QUESTION_ID))

        self.assertIsNotNone(element)
        self.assertIsNotNone(question)
        self.assertEqual(question.knowledge_element_id, element.id)

    async def test_removed_element_with_learning_history_is_deactivated(self) -> None:
        await self.synchronize()
        async with self.session_factory() as session:
            element = await session.scalar(
                select(KnowledgeElement).where(KnowledgeElement.external_id == KNOWLEDGE_ID)
            )
            question = await session.scalar(select(Question).where(Question.external_id == QUESTION_ID))
            self.assertIsNotNone(element)
            self.assertIsNotNone(question)
            user = User(telegram_id=101, username="fixture-user")
            session.add(user)
            await session.flush()
            session.add(Progress(user_id=user.id, knowledge_element_id=element.id))
            session.add(
                Attempt(
                    user_id=user.id,
                    question_id=question.id,
                    answer="fixture answer",
                    verdict=AttemptVerdict.INCORRECT,
                )
            )
            await session.commit()
            element_id = element.id
            question_id = question.id

        shutil.rmtree(self.fixture_directory)
        report = await self.synchronize()

        async with self.session_factory() as session:
            element = await session.scalar(
                select(KnowledgeElement).where(KnowledgeElement.external_id == KNOWLEDGE_ID)
            )
            question = await session.scalar(select(Question).where(Question.external_id == QUESTION_ID))
            progress = await session.scalar(
                select(Progress).where(Progress.knowledge_element_id == element_id)
            )
            attempt = await session.scalar(select(Attempt).where(Attempt.question_id == question_id))

        self.assertEqual(report.deactivated_knowledge_elements, 1)
        self.assertEqual(element.id, element_id)
        self.assertFalse(element.is_active)
        self.assertFalse(question.is_active)
        self.assertIsNotNone(progress)
        self.assertIsNotNone(attempt)

    async def test_invalid_file_does_not_apply_partial_changes(self) -> None:
        questions_path = self.fixture_directory / "questions.json"
        payload = json.loads(questions_path.read_text(encoding="utf-8"))
        payload["questions"][0]["knowledge_id"] = "test-fixture.validation-fixture.missing"
        questions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(TheoryValidationError, "unknown knowledge_id"):
            await self.synchronize()

        async with self.session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count(Source.id))), 0)
            self.assertEqual(await session.scalar(select(func.count(KnowledgeElement.id))), 0)
            self.assertEqual(await session.scalar(select(func.count(Question.id))), 0)
