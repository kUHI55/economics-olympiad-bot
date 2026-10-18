import asyncio
import base64
import io
import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from wsgiref.util import setup_testing_defaults

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database.models  # noqa: F401
import app.web.application as web_module
from app.core.enums import AttemptVerdict, QuestionType
from app.database.base import Base
from app.database.models.learning import Attempt, Progress, ReviewSchedule
from app.services.theory.importer import TheoryImporter
from app.web.application import TheoryWebApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEORY_ROOT = PROJECT_ROOT / "data" / "theory"


def request(application, path: str, method: str = "GET", body: bytes = b"", headers=None):
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
    )
    for name, value in (headers or {}).items():
        environ[name] = value
    result = {}

    def start_response(status, response_headers):
        result["status"] = status
        result["headers"] = dict(response_headers)

    result["body"] = b"".join(application(environ, start_response))
    return result


class TheoryWebRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = TheoryWebApplication()

    def test_homepage_and_topic_catalog_are_served(self) -> None:
        homepage = request(self.application, "/")
        catalog = request(self.application, "/api/theory")
        payload = json.loads(catalog["body"])

        self.assertTrue(homepage["status"].startswith("200"))
        self.assertIn("Темы".encode(), request(self.application, "/static/app.js")["body"])
        themes = {theme["id"]: theme for theme in payload["themes"]}
        self.assertEqual(themes["mathematical-base"]["title"], "Математика")
        self.assertEqual(themes["utility-and-consumer"]["title"], "Полезность и потребитель")
        self.assertEqual(themes["monopoly"]["title"], "Монополия")
        self.assertEqual(
            set(themes),
            {"mathematical-base", "utility-and-consumer", "monopoly"},
        )
        self.assertNotIn("demo", themes)
        self.assertGreaterEqual(themes["mathematical-base"]["construction_count"], 14)
        self.assertEqual(
            sum(len(subtopic["questions"]) for subtopic in themes["mathematical-base"]["subtopics"]),
            58,
        )
        self.assertEqual(themes["mathematical-base"]["knowledge_count"], 54)
        self.assertEqual(themes["utility-and-consumer"]["knowledge_count"], 38)
        self.assertEqual(themes["utility-and-consumer"]["question_count"], 38)
        self.assertEqual(themes["monopoly"]["knowledge_count"], 18)
        self.assertEqual(themes["monopoly"]["question_count"], 23)
        self.assertEqual(len(themes["monopoly"]["subtopics"]), 18)
        self.assertEqual(len(payload["themes"]), 3)
        self.assertTrue(
            all(
                subtopic["knowledge"] and subtopic["questions"]
                for theme in themes.values()
                for subtopic in theme["subtopics"]
            )
        )
        self.assertTrue(
            all(
                "reference_answer" not in question and "correct_answer" not in question
                for theme in payload["themes"]
                for topic in theme["subtopics"]
                for question in topic["questions"]
            )
        )

    def test_all_active_quiz_questions_have_four_distinct_keyed_choices(self) -> None:
        repository = web_module.load_theory_repository(THEORY_ROOT)
        questions = [
            question
            for topic in repository.topics
            if not topic.knowledge.is_demo
            for question in topic.questions.questions
        ]
        self.assertEqual(len(questions), 119)
        for question in questions:
            with self.subTest(question_id=question.id):
                self.assertIs(question.type, QuestionType.MULTIPLE_CHOICE)
                self.assertEqual(len(question.options), 4)
                texts = [option.text.strip() for option in question.options]
                self.assertTrue(all(texts))
                self.assertEqual(len({text.casefold() for text in texts}), 4)
                correct = [
                    option for option in question.options
                    if option.id == question.correct_answer
                ]
                self.assertEqual(len(correct), 1)
                self.assertEqual(correct[0].text, question.reference_answer)
                self.assertTrue(question.explanation.strip())

    def test_quiz_frontend_uses_choices_and_retains_submission_state(self) -> None:
        script = request(self.application, "/static/app.js")["body"].decode()
        self.assertIn('input type="radio" name="answer"', script)
        self.assertNotIn("<textarea", script)
        self.assertIn("form.addEventListener(\"submit\", submitAnswer)", script)
        self.assertIn("state.selectedAnswer", script)
        self.assertIn('data-action="next-question"', script)
        self.assertIn("renderQuizSummary", script)
        self.assertIn("recordLocalAttempt(question, answer, result)", script)
        self.assertIn("state.answered ? \"disabled\"", script)
        self.assertIn("allQuestions().filter", script)
        self.assertIn("popstate", script)
        self.assertIn("renderStatistics", script)
        self.assertTrue(request(self.application, "/static/learning.js")["status"].startswith("200"))

    def test_local_quiz_start_and_review_do_not_require_database_password(self) -> None:
        script = request(self.application, "/static/app.js")["body"].decode()
        self.assertIn('action === "start-theme-quiz"', script)
        self.assertIn('action === "start-global-quiz"', script)
        self.assertIn('state.progress.answer_mode === "database" && !context.forceLocal', script)
        self.assertIn('state.pendingQuiz = { questions: selected, count, ensureThemeCoverage, context }', script)
        self.assertIn('action === "continue-local-quiz"', script)
        self.assertIn('EcolabLearning.reviewQuestionIds(state.learning)', script)
        self.assertIn('state.progress.answer_mode === "local"', script)
        self.assertIn('state.quizSession?.local === true', script)
        self.assertIn('state.questions = selected;', script)

    def test_local_answer_mode_can_be_explicitly_selected_without_password(self) -> None:
        question = next(
            question
            for topic in web_module.load_theory_repository(THEORY_ROOT).topics
            for question in topic.questions.questions
        )
        correct_index = next(
            index for index, option in enumerate(question.options)
            if option.id == question.correct_answer
        )
        body = json.dumps({
            "mode": "local", "question_id": question.id, "answer": str(correct_index),
        }).encode()
        with (
            patch.dict("os.environ", {"WEB_PASSWORD": "configured"}),
            patch.object(self.application, "_database_settings", side_effect=AssertionError("local mode must not query DB config")),
        ):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=body,
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )
        payload = json.loads(result["body"])
        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(payload["verdict"], "correct")
        self.assertFalse(payload["progress_saved"])

    def test_monopoly_construction_cards_have_quizzes(self) -> None:
        notes_path = THEORY_ROOT / "monopoly" / "problem-constructions.md"
        source = notes_path.read_text(encoding="utf-8")
        construction_headings = [
            line
            for line in source.splitlines()
            if line.startswith("## ") and line[3:4].isdigit()
        ]
        repository = web_module.load_theory_repository(THEORY_ROOT)
        monopoly_questions = [
            question.id
            for topic in repository.topics
            if topic.knowledge.section == "monopoly"
            for question in topic.questions.questions
        ]
        script = request(self.application, "/static/app.js")["body"].decode()

        self.assertEqual(len(construction_headings), 16)
        for construction_number in range(1, 17):
            marker = f".construction-{construction_number:02d}-"
            self.assertTrue(any(marker in question_id for question_id in monopoly_questions))
        self.assertIn("current.body.push", script)
        self.assertIn('data-action="construction-quiz:', script)

    def test_study_interface_and_companion_documents_are_served(self) -> None:
        script = request(self.application, "/static/app.js")
        constructions = request(
            self.application,
            "/api/documents/mathematical-base/problem-constructions.md",
        )
        review = request(self.application, "/api/documents/mathematical-base/review-sheet.md")
        utility_notes = request(
            self.application,
            "/api/documents/utility-and-consumer/study-notes.md",
        )
        utility_constructions = request(
            self.application,
            "/api/documents/utility-and-consumer/problem-constructions.md",
        )
        utility_review = request(
            self.application,
            "/api/documents/utility-and-consumer/review-sheet.md",
        )
        monopoly_notes = request(
            self.application,
            "/api/documents/monopoly/study-notes.md",
        )
        monopoly_constructions = request(
            self.application,
            "/api/documents/monopoly/problem-constructions.md",
        )
        monopoly_review = request(
            self.application,
            "/api/documents/monopoly/review-sheet.md",
        )

        self.assertTrue(script["status"].startswith("200"))
        self.assertIn(b"submitAnswer", script["body"])
        self.assertIn(b"next-question", script["body"])
        self.assertIn("Правильный ответ:".encode(), script["body"])
        self.assertTrue(constructions["status"].startswith("200"))
        self.assertTrue(review["status"].startswith("200"))
        self.assertTrue(utility_notes["status"].startswith("200"))
        self.assertIn("Карта всех 24 задач".encode(), utility_notes["body"])
        self.assertTrue(utility_constructions["status"].startswith("200"))
        self.assertTrue(utility_review["status"].startswith("200"))
        self.assertTrue(monopoly_notes["status"].startswith("200"))
        self.assertTrue(monopoly_constructions["status"].startswith("200"))
        self.assertTrue(monopoly_review["status"].startswith("200"))
        self.assertIn("Карта анализа всех 30 слайдов".encode(), monopoly_notes["body"])
        self.assertIn("карта задач 1–24".encode(), monopoly_notes["body"])
        self.assertIn("задачи 25–33".encode(), monopoly_notes["body"])
        self.assertIn("56−8√19".encode(), monopoly_notes["body"])
        self.assertIn("совместимости стимулов".encode(), monopoly_constructions["body"])
        self.assertIn("Индекс Лернера".encode(), monopoly_review["body"])

    def test_full_user_report_is_served_without_rewriting(self) -> None:
        result = request(self.application, "/api/documents/study-notes.md")
        source = (THEORY_ROOT / "mathematical-base" / "study-notes.md").read_bytes()

        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(result["body"], source)
        self.assertGreater(len(result["body"].splitlines()), 1600)

    def test_answer_submission_requires_site_password(self) -> None:
        body = json.dumps({"question_id": "math.test", "answer": "a"}).encode()
        with (
            patch.object(self.application, "_database_settings", return_value=SimpleNamespace(database_url="postgresql://configured")),
            patch.object(self.application, "_database_available", new=AsyncMock(return_value=True)),
            patch.dict("os.environ", {"WEB_PASSWORD": "correct-horse"}),
        ):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=body,
                headers={
                    "CONTENT_TYPE": "application/json",
                    "HTTP_AUTHORIZATION": "Basic " + base64.b64encode(b"student:wrong").decode(),
                },
            )

        self.assertTrue(result["status"].startswith("401"))
        self.assertIn("WWW-Authenticate", result["headers"])

    def test_configured_database_without_web_password_keeps_loopback_quiz_local(self) -> None:
        repository = web_module.load_theory_repository(THEORY_ROOT)
        question = next(
            item for topic in repository.topics for item in topic.questions.questions
            if item.options
        )
        answer = str(next(
            index for index, option in enumerate(question.options)
            if option.id == question.correct_answer
        ))
        body = json.dumps({"question_id": question.id, "answer": answer}).encode()
        settings = SimpleNamespace(database_url="postgresql://configured")
        with (
            patch.object(self.application, "_database_settings", return_value=settings),
            patch.object(self.application, "_database_available", new=AsyncMock(return_value=True)),
            patch.dict("os.environ", {"WEB_PASSWORD": ""}),
            patch.object(web_module, "get_settings", return_value=settings),
        ):
            result = request(
                self.application, "/api/answer", method="POST", body=body,
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )
            progress = asyncio.run(self.application._progress_payload())
        payload = json.loads(result["body"])
        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(payload["verdict"], "correct")
        self.assertFalse(payload["progress_saved"])
        self.assertEqual(progress["answer_mode"], "local")

    def test_unavailable_configured_database_falls_back_to_loopback_quiz(self) -> None:
        question_document = json.loads(
            (
                THEORY_ROOT
                / "utility-and-consumer"
                / "problem-set-and-workshop"
                / "questions.json"
            ).read_text(encoding="utf-8")
        )
        question = next(
            item for item in question_document["questions"]
            if item["id"].endswith(".problem-map.recall")
        )
        correct_index = next(
            index for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )
        body = json.dumps({"question_id": question["id"], "answer": str(correct_index)}).encode()
        with (
            patch.object(self.application, "_database_settings", return_value=SimpleNamespace(database_url="postgresql://unavailable")),
            patch.object(self.application, "_database_available", new=AsyncMock(return_value=False)),
        ):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=body,
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )

        payload = json.loads(result["body"])
        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(payload["verdict"], "correct")
        self.assertFalse(payload["progress_saved"])

    def test_local_answer_route_checks_json_without_password_or_database(self) -> None:
        repository = web_module.load_theory_repository(THEORY_ROOT)
        question = next(
            item
            for topic in repository.topics
            for item in topic.questions.questions
            if item.type.value == "multiple_choice"
        )
        correct_index = next(
            index for index, option in enumerate(question.options)
            if option.id == question.correct_answer
        )
        body = json.dumps({"question_id": question.id, "answer": str(correct_index)}).encode()
        with patch.object(self.application, "_database_settings", return_value=None):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=body,
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )
        payload = json.loads(result["body"])
        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(payload["verdict"], "correct")
        self.assertEqual(payload["reference_answer"], question.reference_answer)
        self.assertEqual(payload["explanation"], question.explanation)
        self.assertFalse(payload["progress_saved"])

    def test_monopoly_answers_are_checked_locally_with_explanation(self) -> None:
        question_document = json.loads(
            (
                THEORY_ROOT
                / "monopoly"
                / "03-profit-optimization"
                / "questions.json"
            ).read_text(encoding="utf-8")
        )
        question = question_document["questions"][0]
        correct_index = next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )
        wrong_index = (correct_index + 1) % len(question["options"])
        with patch.object(self.application, "_database_settings", return_value=None):
            correct = request(
                self.application,
                "/api/answer",
                method="POST",
                body=json.dumps(
                    {"question_id": question["id"], "answer": str(correct_index)}
                ).encode(),
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )
            incorrect = request(
                self.application,
                "/api/answer",
                method="POST",
                body=json.dumps(
                    {"question_id": question["id"], "answer": str(wrong_index)}
                ).encode(),
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )

        correct_payload = json.loads(correct["body"])
        incorrect_payload = json.loads(incorrect["body"])
        self.assertEqual(correct_payload["verdict"], "correct")
        self.assertEqual(incorrect_payload["verdict"], "incorrect")
        self.assertEqual(incorrect_payload["reference_answer"], question["reference_answer"])
        self.assertEqual(incorrect_payload["explanation"], question["explanation"])
        self.assertFalse(incorrect_payload["progress_saved"])

    def test_utility_theme_quiz_checks_choice_and_explains_incorrect_answer(self) -> None:
        question_document = json.loads(
            (
                THEORY_ROOT
                / "utility-and-consumer"
                / "problem-set-and-workshop"
                / "questions.json"
            ).read_text(encoding="utf-8")
        )
        question = next(
            item
            for item in question_document["questions"]
            if item["id"].endswith(".problem-map.recall")
        )
        wrong_index = next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] != question["correct_answer"]
        )
        body = json.dumps(
            {"question_id": question["id"], "answer": str(wrong_index)}
        ).encode()
        with patch.object(self.application, "_database_settings", return_value=None):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=body,
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "127.0.0.1"},
            )

        payload = json.loads(result["body"])
        self.assertTrue(result["status"].startswith("200"))
        self.assertEqual(payload["verdict"], "incorrect")
        self.assertEqual(payload["reference_answer"], question["reference_answer"])
        self.assertEqual(payload["explanation"], question["explanation"])
        self.assertFalse(payload["progress_saved"])

    def test_local_answer_route_rejects_non_loopback_clients(self) -> None:
        with patch.object(self.application, "_database_settings", return_value=None):
            result = request(
                self.application,
                "/api/answer",
                method="POST",
                body=json.dumps({"question_id": "unknown", "answer": "x"}).encode(),
                headers={"CONTENT_TYPE": "application/json", "REMOTE_ADDR": "192.0.2.10"},
            )
        self.assertTrue(result["status"].startswith("403"))

    def test_progress_endpoint_reports_file_backed_local_mode(self) -> None:
        with patch.object(self.application, "_database_settings", return_value=None):
            result = asyncio.run(self.application._progress_payload())
        self.assertEqual(result["answer_mode"], "local")
        self.assertFalse(result["available"])

    def test_progress_endpoint_uses_local_mode_when_configured_database_is_down(self) -> None:
        settings = SimpleNamespace(database_url="postgresql://unavailable")
        with (
            patch.object(web_module, "get_settings", return_value=settings),
            patch.object(self.application, "_database_available", new=AsyncMock(return_value=False)),
        ):
            result = asyncio.run(self.application._progress_payload())
        self.assertEqual(result["answer_mode"], "local")
        self.assertFalse(result["available"])


class LocalAnswerCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repository = web_module.load_theory_repository(THEORY_ROOT)
        cls.questions = [
            question
            for topic in repository.topics
            for question in topic.questions.questions
        ]

    def test_supported_multiple_choice_formula_and_free_response_types(self) -> None:
        from app.web.answer_checker import check_local_answer

        multiple_choice = next(q for q in self.questions if q.type.value == "multiple_choice")
        correct_index = next(i for i, option in enumerate(multiple_choice.options) if option.id == multiple_choice.correct_answer)
        result = check_local_answer(multiple_choice, str(correct_index))
        self.assertEqual(result["verdict"], "correct")

        formula_source = self.questions[0]
        formula = formula_source.model_copy(
            update={"type": QuestionType.FORMULA, "options": [], "correct_answer": None}
        )
        exact_formula = check_local_answer(formula, formula.reference_answer)
        self.assertEqual(exact_formula["verdict"], "correct")
        self.assertFalse(exact_formula["progress_saved"])

        free_response = formula.model_copy(
            update={"type": QuestionType.UNDERSTANDING, "reference_answer": "эталонный текст"}
        )
        uncertain = check_local_answer(free_response, "ответ своими словами, требующий проверки")
        self.assertEqual(uncertain["verdict"], "uncertain")
        self.assertIsNone(uncertain["score"])

    def test_unsupported_formula_is_not_marked_incorrect(self) -> None:
        from app.web.answer_checker import check_local_answer

        formula_source = self.questions[0]
        formula = formula_source.model_copy(
            update={"type": QuestionType.FORMULA, "options": [], "correct_answer": None}
        )
        result = check_local_answer(formula, "sqrt(x) + ln(y)")
        self.assertEqual(result["verdict"], "uncertain")

    def test_each_present_question_type_accepts_its_exact_reference(self) -> None:
        from app.web.answer_checker import check_local_answer

        questions_by_type = {}
        for question in self.questions:
            questions_by_type.setdefault(question.type, question)
        self.assertEqual({kind.value for kind in questions_by_type}, {"multiple_choice"})
        question = questions_by_type[QuestionType.MULTIPLE_CHOICE]
        answer = str(next(
            index for index, option in enumerate(question.options)
            if option.id == question.correct_answer
        ))
        with self.subTest(question_type="multiple_choice"):
            self.assertEqual(check_local_answer(question, answer)["verdict"], "correct")


class WebsiteProgressPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "theory"
        self.topic_directory = self.root / "ppc-mathematics"
        self.topic_directory.mkdir(parents=True)
        for name in ("knowledge.json", "questions.json"):
            shutil.copy(
                THEORY_ROOT / "mathematical-base" / "ppc-mathematics" / name,
                self.topic_directory / name,
            )
        self.database_url = f"sqlite+aiosqlite:///{self.root.parent / 'website-tests.sqlite'}"
        self.engine = create_async_engine(self.database_url)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            await TheoryImporter(session).synchronize(self.root)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temporary_directory.cleanup()

    async def test_checked_answer_is_saved_to_existing_progress_tables(self) -> None:
        question_doc = json.loads((self.topic_directory / "questions.json").read_text(encoding="utf-8"))
        question = question_doc["questions"][0]
        correct_index = next(
            index for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )

        settings = SimpleNamespace(
            database_url=self.database_url,
            admin_id=123456,
            llm_api_key=None,
            llm_model="unused",
        )
        with patch.object(web_module, "get_settings", return_value=settings):
            result = await TheoryWebApplication(self.root)._save_answer(
                {"question_id": question["id"], "answer": str(correct_index)}
            )

        async with self.factory() as session:
            attempt = await session.scalar(select(Attempt))
            attempts = await session.scalar(select(func.count()).select_from(Attempt))
            progress = await session.scalar(select(Progress))
            schedule = await session.scalar(select(ReviewSchedule))
        self.assertEqual(result["verdict"], "correct")
        self.assertEqual(attempts, 1)
        self.assertEqual(attempt.answer, question["options"][correct_index]["text"])
        self.assertEqual(progress.attempts_count, 1)
        self.assertEqual(progress.correct_count, 1)
        self.assertEqual(schedule.success_count, 1)
        self.assertEqual(schedule.interval_days, 3)

    async def test_incorrect_answer_returns_feedback_and_updates_progress(self) -> None:
        question_doc = json.loads((self.topic_directory / "questions.json").read_text(encoding="utf-8"))
        question = question_doc["questions"][0]
        incorrect_index = next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] != question["correct_answer"]
        )
        settings = SimpleNamespace(
            database_url=self.database_url,
            admin_id=123456,
            llm_api_key=None,
            llm_model="unused",
        )
        application = TheoryWebApplication(self.root)
        with (
            patch.object(web_module, "get_settings", return_value=settings),
            patch.dict("os.environ", {"WEB_PASSWORD": "configured"}),
        ):
            result = await application._save_answer(
                {"question_id": question["id"], "answer": str(incorrect_index)}
            )
            progress_payload = await application._progress_payload()

        async with self.factory() as session:
            attempt = await session.scalar(select(Attempt))
            progress = await session.scalar(select(Progress))
            schedule = await session.scalar(select(ReviewSchedule))
        self.assertEqual(result["verdict"], "incorrect")
        self.assertEqual(result["reference_answer"], question["reference_answer"])
        self.assertEqual(result["explanation"], question["explanation"])
        self.assertEqual(attempt.verdict, AttemptVerdict.INCORRECT)
        self.assertEqual(progress.attempts_count, 1)
        self.assertEqual(progress.incorrect_count, 1)
        self.assertEqual(schedule.failure_count, 1)
        self.assertTrue(progress_payload["available"])
        self.assertGreaterEqual(progress_payload["themes"]["mathematical-base"]["studied"], 1)

    async def test_due_error_survives_app_restart_and_clears_after_correct_answer(self) -> None:
        question_doc = json.loads((self.topic_directory / "questions.json").read_text(encoding="utf-8"))
        question = question_doc["questions"][0]
        correct_index = next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )
        wrong_index = next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] != question["correct_answer"]
        )
        settings = SimpleNamespace(
            database_url=self.database_url,
            admin_id=123456,
            llm_api_key=None,
            llm_model="unused",
        )
        with patch.object(web_module, "get_settings", return_value=settings):
            await TheoryWebApplication(self.root)._save_answer(
                {"question_id": question["id"], "answer": str(wrong_index)}
            )
            async with self.factory() as session:
                schedule = await session.scalar(select(ReviewSchedule))
                schedule.next_review = datetime.now(UTC) - timedelta(days=1)
                await session.commit()

            # A fresh application and engine must read the previously saved review state.
            restarted_application = TheoryWebApplication(self.root)
            due = await restarted_application._review_question_ids()
            self.assertIn(question["id"], due["question_ids"])

            await restarted_application._save_answer(
                {"question_id": question["id"], "answer": str(correct_index)}
            )
            async with self.factory() as session:
                schedule = await session.scalar(select(ReviewSchedule))
                schedule.next_review = datetime.now(UTC) - timedelta(days=1)
                await session.commit()

            after_correction = await TheoryWebApplication(self.root)._review_question_ids()

        self.assertNotIn(question["id"], after_correction["question_ids"])

    async def test_web_quiz_session_links_attempts_prevents_duplicates_and_reports_completion(self) -> None:
        question_doc = json.loads((self.topic_directory / "questions.json").read_text(encoding="utf-8"))
        question = question_doc["questions"][0]
        correct_index = next(
            index for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )
        settings = SimpleNamespace(
            database_url=self.database_url, admin_id=123456, llm_api_key=None, llm_model="unused"
        )
        application = TheoryWebApplication(self.root)
        with patch.object(web_module, "get_settings", return_value=settings):
            created = await application._start_web_session({
                "question_ids": [question["id"]],
                "context": {"type": "subtopic", "label": "Математика"},
            })
            session_id = created["session_id"]
            first = await application._save_answer({
                "question_id": question["id"], "answer": str(correct_index), "session_id": session_id,
            })
            duplicate = await application._save_answer({
                "question_id": question["id"], "answer": str((correct_index + 1) % 4), "session_id": session_id,
            })
            result = await application._complete_web_session(str(session_id))
            statistics = await application._database_statistics()

        async with self.factory() as session:
            attempt_count = await session.scalar(select(func.count()).select_from(Attempt))
            quiz_session = await session.get(web_module.QuizSession, session_id)
        self.assertEqual(attempt_count, 1)
        self.assertEqual(first["verdict"], "correct")
        self.assertTrue(duplicate["duplicate_submission"])
        self.assertEqual(duplicate["verdict"], "correct")
        self.assertEqual(result, {"completed": True, "total": 1, "correct": 1})
        self.assertIsNotNone(quiz_session.completed_at)
        self.assertEqual(len(statistics["sessions"]), 1)
        self.assertEqual(statistics["sessions"][0]["status"], "completed")
        self.assertEqual(len(statistics["sessions"][0]["attempts"]), 1)

    async def test_web_session_links_attempts_prevents_duplicates_and_reports_completion(self) -> None:
        question_doc = json.loads((self.topic_directory / "questions.json").read_text(encoding="utf-8"))
        question = question_doc["questions"][0]
        correct_index = next(
            index for index, option in enumerate(question["options"])
            if option["id"] == question["correct_answer"]
        )
        settings = SimpleNamespace(
            database_url=self.database_url, admin_id=123456, llm_api_key=None, llm_model="unused"
        )
        application = TheoryWebApplication(self.root)
        with patch.object(web_module, "get_settings", return_value=settings):
            created = await application._start_web_session({
                "question_ids": [question["id"]],
                "context": {"type": "subtopic", "label": "Математика"},
            })
            session_id = created["session_id"]
            first = await application._save_answer({
                "question_id": question["id"], "answer": str(correct_index), "session_id": session_id,
            })
            duplicate = await application._save_answer({
                "question_id": question["id"], "answer": str((correct_index + 1) % 4), "session_id": session_id,
            })
            result = await application._complete_web_session(str(session_id))
            statistics = await application._database_statistics()

        async with self.factory() as session:
            attempt_count = await session.scalar(select(func.count()).select_from(Attempt))
            quiz_session = await session.get(web_module.QuizSession, session_id)
        self.assertEqual(attempt_count, 1)
        self.assertEqual(first["verdict"], "correct")
        self.assertTrue(duplicate["duplicate_submission"])
        self.assertEqual(duplicate["verdict"], "correct")
        self.assertEqual(result, {"completed": True, "total": 1, "correct": 1})
        self.assertIsNotNone(quiz_session.completed_at)
        self.assertEqual(len(statistics["sessions"]), 1)
        self.assertEqual(statistics["sessions"][0]["status"], "completed")
        self.assertEqual(len(statistics["sessions"][0]["attempts"]), 1)
