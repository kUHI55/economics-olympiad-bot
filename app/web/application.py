"""Small WSGI site; content stays in the checked-in theory repository."""

import asyncio
import base64
import hmac
import json
import os
import re
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.enums import AttemptVerdict, QuestionType, QuizMode
from app.database.models.catalog import Section, Subtopic, Topic
from app.database.models.content import KnowledgeElement, Question
from app.database.models.learning import (
    Attempt,
    Progress,
    QuizSession,
    ReviewSchedule,
    SessionQuestion,
)
from app.database.models.user import User
from app.database.repositories.user import UserRepository
from app.services.llm.client import UnavailableLlmClient
from app.services.llm.openai_client import OpenAiLlmClient
from app.services.progress.service import ProgressService
from app.services.quiz.evaluator import AnswerEvaluationService
from app.theory_data.validator import load_theory_repository
from app.web.answer_checker import check_local_answer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
THEORY_ROOT = PROJECT_ROOT / "data" / "theory"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DOCUMENTS = {"study-notes.md", "problem-constructions.md", "review-sheet.md"}
CONSTRUCTION_QUESTION_MARKER = ".construction-"


class WebRequestError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        self.status = status
        self.message = message


class TheoryWebApplication:
    def __init__(self, theory_root: Path = THEORY_ROOT, static_root: Path = STATIC_ROOT) -> None:
        self.theory_root = theory_root
        self.static_root = static_root

    def __call__(self, environ: dict[str, Any], start_response) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = unquote(environ.get("PATH_INFO", "/"))
        try:
            if method == "GET" and path == "/":
                return self._respond(start_response, HTTPStatus.OK, self._read_static("index.html"), "text/html; charset=utf-8")
            if method == "GET" and path.startswith("/static/"):
                return self._static_response(path, start_response)
            if method == "GET" and path == "/api/theory":
                return self._json_response(start_response, HTTPStatus.OK, self._theory_payload())
            if method == "GET" and path == "/api/progress":
                return self._json_response(
                    start_response, HTTPStatus.OK, asyncio.run(self._progress_payload())
                )
            if method == "GET" and path == "/api/statistics":
                self._require_web_password(environ)
                return self._json_response(
                    start_response, HTTPStatus.OK, asyncio.run(self._database_statistics())
                )
            if method == "POST" and path == "/api/quiz-sessions":
                self._require_web_password(environ)
                return self._json_response(
                    start_response, HTTPStatus.CREATED,
                    asyncio.run(self._start_web_session(self._read_json_body(environ))),
                )
            if method == "POST" and path.startswith("/api/quiz-sessions/") and path.endswith("/complete"):
                self._require_web_password(environ)
                session_id = path.removeprefix("/api/quiz-sessions/").removesuffix("/complete").strip("/")
                return self._json_response(
                    start_response, HTTPStatus.OK,
                    asyncio.run(self._complete_web_session(session_id, self._read_json_body(environ))),
                )
            if method == "GET" and path == "/api/review-questions":
                self._require_web_password(environ)
                return self._json_response(
                    start_response, HTTPStatus.OK, asyncio.run(self._review_question_ids())
                )
            if method == "GET" and path.startswith("/api/documents/"):
                return self._document_response(path, start_response)
            if method == "POST" and path == "/api/answer":
                body = self._read_json_body(environ)
                if body.get("mode") == "local":
                    self._require_local_request(environ)
                    result = self._check_answer_from_files(body)
                else:
                    settings = self._database_settings()
                    database_available = (
                        bool(os.getenv("WEB_PASSWORD"))
                        and settings is not None
                        and asyncio.run(self._database_available(settings))
                    )
                    if not database_available:
                        self._require_local_request(environ)
                        result = self._check_answer_from_files(body)
                    else:
                        self._require_web_password(environ)
                        result = asyncio.run(self._save_answer(body))
                return self._json_response(start_response, HTTPStatus.OK, result)
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Страница не найдена."})
        except WebRequestError as error:
            if error.status is HTTPStatus.UNAUTHORIZED:
                body = json.dumps({"error": error.message}, ensure_ascii=False).encode("utf-8")
                start_response(
                    "401 Unauthorized",
                    [
                        ("Content-Type", "application/json; charset=utf-8"),
                        ("Content-Length", str(len(body))),
                        ("WWW-Authenticate", 'Basic realm="Economics theory", charset="UTF-8"'),
                        ("X-Content-Type-Options", "nosniff"),
                    ],
                )
                return [body]
            return self._json_response(start_response, error.status, {"error": error.message})
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return self._json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Не удалось обработать запрос."})
        except Exception:
            return self._json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Сервис обучения временно недоступен."})

    def _theory_payload(self) -> dict[str, Any]:
        themes: dict[str, dict[str, Any]] = {}
        for knowledge_path in sorted(self.theory_root.rglob("knowledge.json")):
            knowledge_document = json.loads(knowledge_path.read_text(encoding="utf-8"))
            if knowledge_document.get("is_demo", False):
                continue
            questions_path = knowledge_path.with_name("questions.json")
            question_document = json.loads(questions_path.read_text(encoding="utf-8"))
            section_id = knowledge_document["section"]
            section_directory = self.theory_root / section_id
            theme = themes.setdefault(
                section_id,
                {
                    "id": section_id,
                    "title": self._theme_title(
                        section_directory,
                        knowledge_document.get("section_title") or section_id,
                    ),
                    "description": "",
                    "subtopics": [],
                    "documents": [],
                },
            )
            knowledge_by_id = {
                item["id"]: item for item in knowledge_document["knowledge"]
            }
            subtopic_id = knowledge_document["topic"]
            subtopic = {
                "id": subtopic_id,
                "title": knowledge_document.get("topic_title") or subtopic_id,
                "knowledge": knowledge_document["knowledge"],
                "questions": [
                    {
                        "id": question["id"],
                        "knowledge_id": question["knowledge_id"],
                        "knowledge_type": knowledge_by_id[question["knowledge_id"]]["type"],
                        "knowledge_title": knowledge_by_id[question["knowledge_id"]]["title"],
                        "category": (
                            "construction"
                            if CONSTRUCTION_QUESTION_MARKER in question["id"]
                            or knowledge_by_id[question["knowledge_id"]]["type"]
                            in {"mechanism", "example"}
                            else "theory"
                        ),
                        "type": question["type"],
                        "difficulty": question["difficulty"],
                        "question": question["question"],
                        "options": question.get("options", []),
                    }
                    for question in question_document["questions"]
                ],
            }
            theme["subtopics"].append(subtopic)

            if theme["description"] == "":
                theme["description"] = self._theme_description(
                    section_directory, knowledge_document["knowledge"]
                )
            theme["documents"] = [
                name for name in sorted(DOCUMENTS) if (section_directory / name).is_file()
            ]

        result = []
        for theme in themes.values():
            theme["subtopics"].sort(key=lambda item: item["id"])
            theme["question_count"] = sum(
                len(item["questions"]) for item in theme["subtopics"]
            )
            theme["knowledge_count"] = sum(
                len(item["knowledge"]) for item in theme["subtopics"]
            )
            theme["construction_count"] = sum(
                question["category"] == "construction"
                for item in theme["subtopics"]
                for question in item["questions"]
            )
            result.append(theme)
        return {"themes": result}

    @staticmethod
    def _theme_title(section_directory: Path, fallback: str) -> str:
        notes = section_directory / "study-notes.md"
        if notes.is_file():
            heading = next(
                (
                    line
                    for line in notes.read_text(encoding="utf-8").splitlines()
                    if line.startswith("# ")
                ),
                "",
            )
            match = re.search(r"«([^»]+)»", heading)
            if match:
                return match.group(1)
        return fallback

    @staticmethod
    def _theme_description(section_directory: Path, knowledge: list[dict[str, Any]]) -> str:
        notes = section_directory / "study-notes.md"
        if notes.is_file():
            lines = notes.read_text(encoding="utf-8").splitlines()
            heading = next((line for line in lines if line.startswith("# ")), "")
            match = re.search(r"«([^»]+)»", heading)
            if match:
                return f"Учебная тема «{match.group(1)}» из подготовленных материалов."
        if knowledge:
            description = " ".join(knowledge[0]["explanation"].split())
            return description[:177].rsplit(" ", 1)[0] + "…" if len(description) > 180 else description
        return "Материалы темы и тренировки по её подразделам."

    async def _progress_payload(self) -> dict[str, Any]:
        settings = self._database_settings()
        if (
            settings is None
            or not os.getenv("WEB_PASSWORD")
            or not await self._database_available(settings)
        ):
            return {"available": False, "answer_mode": "local", "themes": {}}
        try:
            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    user_id = await session.scalar(
                        select(User.id).where(User.telegram_id == settings.admin_id)
                    )
                    query = (
                        select(
                            Section.external_id,
                            func.avg(func.coalesce(Progress.mastery_score, 0.0)),
                            func.count(KnowledgeElement.id),
                            func.count(Progress.id),
                        )
                        .join(Topic, Topic.section_id == Section.id)
                        .join(KnowledgeElement, KnowledgeElement.topic_id == Topic.id)
                        .outerjoin(
                            Progress,
                            (Progress.knowledge_element_id == KnowledgeElement.id)
                            & (Progress.user_id == (user_id or -1)),
                        )
                        .where(KnowledgeElement.is_active.is_(True))
                        .group_by(Section.external_id)
                    )
                    rows = (await session.execute(query)).all()
                    return {
                        "available": True,
                        "answer_mode": "database",
                        "themes": {
                            (external_id or "").removeprefix("section:"): {
                                "percent": round(float(average or 0) * 100),
                                "studied": int(studied),
                                "total": int(total),
                            }
                            for external_id, average, total, studied in rows
                        },
                    }
            finally:
                await engine.dispose()
        except Exception:
            return {"available": False, "answer_mode": "local", "themes": {}}

    async def _review_question_ids(self) -> dict[str, Any]:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                user_id = await session.scalar(
                    select(User.id).where(User.telegram_id == settings.admin_id)
                )
                if user_id is None:
                    return {"question_ids": []}
                now = datetime.now(UTC)
                latest_attempt_id = (
                    select(func.max(Attempt.id))
                    .where(Attempt.user_id == user_id, Attempt.question_id == Question.id)
                    .correlate(Question)
                    .scalar_subquery()
                )
                question_ids = await session.scalars(
                    select(Question.external_id)
                    .join(Attempt, Attempt.question_id == Question.id)
                    .join(
                        ReviewSchedule,
                        ReviewSchedule.knowledge_element_id == Question.knowledge_element_id,
                    )
                    .where(
                        Attempt.user_id == user_id,
                        Attempt.id == latest_attempt_id,
                        Attempt.verdict.in_(
                            [
                                AttemptVerdict.INCORRECT,
                                AttemptVerdict.PARTIAL,
                                AttemptVerdict.UNCERTAIN,
                            ]
                        ),
                        ReviewSchedule.user_id == user_id,
                        ReviewSchedule.next_review <= now,
                        Question.is_active.is_(True),
                    )
                    .distinct()
                    .order_by(Question.external_id)
                    .limit(100)
                )
                return {"question_ids": [value for value in question_ids if value]}
        finally:
            await engine.dispose()

    async def _start_web_session(self, body: dict[str, Any]) -> dict[str, Any]:
        question_ids = body.get("question_ids")
        context = body.get("context") or {}
        if (
            not isinstance(question_ids, list) or not question_ids or len(question_ids) > 100
            or any(not isinstance(value, str) for value in question_ids)
            or len(set(question_ids)) != len(question_ids)
        ):
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Некорректный список вопросов квиза.")
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                user = await UserRepository(session).get_or_create(
                    settings.admin_id, "website", "Web learner", True
                )
                questions = list(await session.scalars(select(Question).where(
                    Question.external_id.in_(question_ids), Question.is_active.is_(True)
                )))
                by_external_id = {question.external_id: question for question in questions}
                if len(by_external_id) != len(question_ids):
                    raise WebRequestError(HTTPStatus.BAD_REQUEST, "Квиз содержит неизвестные или неактивные вопросы.")
                session_row = QuizSession(
                    user_id=user.id, mode=QuizMode.PRACTICE,
                    scope_type=str(context.get("type", "mixed"))[:32],
                    total_questions=len(question_ids),
                    started_at=self._browser_datetime(body.get("started_at"), datetime.now(UTC)),
                )
                session.add(session_row)
                await session.flush()
                session.add_all([
                    SessionQuestion(quiz_session_id=session_row.id,
                        question_id=by_external_id[external_id].id, position=position)
                    for position, external_id in enumerate(question_ids, start=1)
                ])
                await session.commit()
                return {"session_id": session_row.id}
        finally:
            await engine.dispose()

    async def _complete_web_session(
        self, raw_session_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            session_id = int(raw_session_id)
        except ValueError as error:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Некорректный идентификатор сессии.") from error
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                user_id = await session.scalar(select(User.id).where(User.telegram_id == settings.admin_id))
                session_row = await session.get(QuizSession, session_id)
                if session_row is None or session_row.user_id != user_id:
                    raise WebRequestError(HTTPStatus.NOT_FOUND, "Сессия квиза не найдена.")
                answered = await session.scalar(select(func.count(SessionQuestion.id)).where(
                    SessionQuestion.quiz_session_id == session_id,
                    SessionQuestion.completed.is_(True),
                ))
                if int(answered or 0) < session_row.total_questions:
                    raise WebRequestError(HTTPStatus.CONFLICT, "Нельзя завершить квиз до ответа на все вопросы.")
                correct = await session.scalar(select(func.count(Attempt.id)).where(
                    Attempt.quiz_session_id == session_id,
                    Attempt.user_id == user_id,
                    Attempt.verdict == AttemptVerdict.CORRECT,
                ))
                if session_row.completed_at is None:
                    session_row.completed_at = self._browser_datetime(
                        (body or {}).get("ended_at"), datetime.now(UTC)
                    )
                    await session.commit()
                return {"completed": True, "total": session_row.total_questions, "correct": int(correct or 0)}
        finally:
            await engine.dispose()

    async def _database_statistics(self) -> dict[str, Any]:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                user_id = await session.scalar(select(User.id).where(User.telegram_id == settings.admin_id))
                if user_id is None:
                    return {"sessions": [], "activeSessionId": None, "legacyAttempts": 0}
                db_sessions = list(await session.scalars(
                    select(QuizSession).where(QuizSession.user_id == user_id)
                    .order_by(QuizSession.started_at.desc())
                ))
                session_ids = [item.id for item in db_sessions]
                records: dict[int, dict[str, Any]] = {}
                for item in db_sessions:
                    records[item.id] = {
                        "id": f"db-{item.id}", "dbSessionId": item.id,
                        "startedAt": item.started_at.isoformat(),
                        "endedAt": item.completed_at.isoformat() if item.completed_at else None,
                        "status": "completed" if item.completed_at else "in_progress",
                        "questionIds": [], "currentIndex": 0, "attempts": [],
                        "context": {"type": item.scope_type, "themeId": "all", "subtopicId": None, "label": "Квиз"},
                    }
                if session_ids:
                    planned = (await session.execute(
                        select(SessionQuestion.quiz_session_id, Question.external_id,
                            Section.external_id, Section.name, Subtopic.external_id, Subtopic.name)
                        .join(Question, Question.id == SessionQuestion.question_id)
                        .join(KnowledgeElement, KnowledgeElement.id == Question.knowledge_element_id)
                        .join(Section, Section.id == KnowledgeElement.section_id)
                        .outerjoin(Subtopic, Subtopic.id == KnowledgeElement.subtopic_id)
                        .where(SessionQuestion.quiz_session_id.in_(session_ids))
                        .order_by(SessionQuestion.position)
                    )).all()
                    context_rows: dict[int, list[tuple[str, str | None, str, str | None]]] = {}
                    for sid, question_id, section_external, section_name, subtopic_external, subtopic_name in planned:
                        if question_id:
                            records[sid]["questionIds"].append(question_id)
                        theme_id = (section_external or "").removeprefix("section:")
                        subtopic_id = (subtopic_external or "").split("/subtopic:")[-1] if subtopic_external else None
                        context_rows.setdefault(sid, []).append((theme_id, subtopic_id, section_name, subtopic_name))
                    for sid, values in context_rows.items():
                        themes = {row[0] for row in values if row[0]}
                        subtopics = {row[1] for row in values if row[1]}
                        records[sid]["context"] = {
                            "type": records[sid]["context"]["type"],
                            "themeId": next(iter(themes)) if len(themes) == 1 else "all",
                            "subtopicId": next(iter(subtopics)) if len(subtopics) == 1 else None,
                            "label": next((row[2] for row in values), "Квиз") if len(themes) == 1 else "Смешанный квиз",
                        }
                rows = (await session.execute(
                    select(Attempt, Question.external_id, Section.external_id, Subtopic.external_id,
                        KnowledgeElement.external_id, KnowledgeElement.knowledge_type)
                    .join(Question, Question.id == Attempt.question_id)
                    .join(KnowledgeElement, KnowledgeElement.id == Question.knowledge_element_id)
                    .join(Section, Section.id == KnowledgeElement.section_id)
                    .outerjoin(Subtopic, Subtopic.id == KnowledgeElement.subtopic_id)
                    .where(Attempt.user_id == user_id)
                    .order_by(Attempt.answered_at)
                )).all()
                legacy_attempts = 0
                for attempt, question_id, section_external, subtopic_external, knowledge_id, knowledge_type in rows:
                    record = records.get(attempt.quiz_session_id)
                    if record is None:
                        legacy_attempts += 1
                        continue
                    record["attempts"].append({
                        "questionId": question_id,
                        "themeId": (section_external or "").removeprefix("section:"),
                        "subtopicId": (subtopic_external or "").split("/subtopic:")[-1] if subtopic_external else None,
                        "constructionId": knowledge_id if str(knowledge_type) in {"mechanism", "example"} else None,
                        "verdict": attempt.verdict.value,
                        "answeredAt": attempt.answered_at.isoformat(),
                    })
                return {"sessions": list(records.values()), "activeSessionId": None, "legacyAttempts": legacy_attempts}
        finally:
            await engine.dispose()

    @staticmethod
    def _browser_datetime(value: Any, fallback: datetime) -> datetime:
        if value is None:
            return fallback
        if not isinstance(value, str):
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Некорректная дата тренировочной сессии.")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Некорректная дата тренировочной сессии.") from error
        if parsed.tzinfo is None:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Дата сессии должна содержать часовой пояс.")
        return parsed

    def _document_response(self, path: str, start_response) -> list[bytes]:
        parts = path.removeprefix("/api/documents/").split("/")
        if len(parts) == 1:
            section, name = "mathematical-base", parts[0]
        elif len(parts) == 2:
            section, name = parts
        else:
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Документ не найден."})
        if name not in DOCUMENTS:
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Документ не найден."})
        if not re.fullmatch(r"[a-z0-9-]+", section):
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Документ не найден."})
        content_path = self.theory_root / section / name
        if not content_path.is_file():
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Документ не найден."})
        return self._respond(start_response, HTTPStatus.OK, content_path.read_bytes(), "text/markdown; charset=utf-8")

    def _static_response(self, path: str, start_response) -> list[bytes]:
        name = path.removeprefix("/static/")
        if name not in {"app.js", "learning.js", "styles.css"}:
            return self._json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Файл не найден."})
        content_type = "text/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8"
        return self._respond(start_response, HTTPStatus.OK, self._read_static(name), content_type)

    def _read_static(self, name: str) -> bytes:
        return (self.static_root / name).read_bytes()

    @staticmethod
    def _read_json_body(environ: dict[str, Any]) -> dict[str, Any]:
        try:
            length = min(int(environ.get("CONTENT_LENGTH") or 0), 8192)
            body = environ["wsgi.input"].read(length)
            value = json.loads(body)
        except (ValueError, json.JSONDecodeError) as error:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Ожидался JSON-запрос.") from error
        if not isinstance(value, dict):
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Ожидался объект запроса.")
        return value

    @staticmethod
    def _database_settings():
        try:
            settings = get_settings()
        except (ValidationError, SettingsError):
            return None
        return settings if settings.database_url.strip() else None

    @staticmethod
    async def _database_available(settings) -> bool:
        engine = None
        try:
            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            if engine is not None:
                try:
                    await engine.dispose()
                except Exception:
                    pass

    @staticmethod
    def _require_local_request(environ: dict[str, Any]) -> None:
        if environ.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}:
            raise WebRequestError(
                HTTPStatus.FORBIDDEN,
                "Локальная проверка доступна только с этого компьютера.",
            )

    def _check_answer_from_files(self, body: dict[str, Any]) -> dict[str, object]:
        question_id = body.get("question_id")
        answer = body.get("answer")
        if not isinstance(question_id, str) or not isinstance(answer, str) or len(answer) > 2000:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Проверьте идентификатор вопроса и ответ.")

        repository = load_theory_repository(self.theory_root)
        question = next(
            (
                item
                for topic in repository.topics
                if not topic.knowledge.is_demo
                for item in topic.questions.questions
                if item.id == question_id
            ),
            None,
        )
        if question is None:
            raise WebRequestError(HTTPStatus.NOT_FOUND, "Вопрос не найден в активных материалах.")
        try:
            return check_local_answer(question, answer)
        except ValueError as error:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, str(error)) from error

    @staticmethod
    def _require_web_password(environ: dict[str, Any]) -> None:
        expected = os.getenv("WEB_PASSWORD")
        if not expected:
            raise WebRequestError(HTTPStatus.SERVICE_UNAVAILABLE, "Задайте WEB_PASSWORD для отправки ответов.")
        header = environ.get("HTTP_AUTHORIZATION", "")
        try:
            scheme, encoded = header.split(" ", 1)
            username, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError):
            password = ""
            scheme = ""
            username = ""
        if (
            scheme.casefold() != "basic"
            or username != "website"
            or not hmac.compare_digest(password, expected)
        ):
            raise WebRequestError(HTTPStatus.UNAUTHORIZED, "Нужна авторизация для сохранения ответа.")

    async def _save_answer(self, body: dict[str, Any]) -> dict[str, Any]:
        external_id = body.get("question_id")
        answer = body.get("answer")
        if not isinstance(external_id, str) or not isinstance(answer, str) or len(answer) > 2000:
            raise WebRequestError(HTTPStatus.BAD_REQUEST, "Проверьте идентификатор вопроса и ответ.")
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        llm = (
            OpenAiLlmClient(settings.llm_api_key.get_secret_value(), settings.llm_model)
            if settings.llm_api_key
            else UnavailableLlmClient()
        )
        try:
            async with factory() as session:
                question = await session.scalar(
                    select(Question)
                    .options(
                        selectinload(Question.options),
                        selectinload(Question.knowledge_element),
                    )
                    .where(Question.external_id == external_id, Question.is_active.is_(True))
                )
                if question is None:
                    raise WebRequestError(HTTPStatus.NOT_FOUND, "Вопрос не найден в синхронизированной базе.")
                saved_answer = answer
                if question.question_type.value == "multiple_choice":
                    try:
                        option_index = int(answer)
                    except (ValueError, IndexError) as error:
                        raise WebRequestError(HTTPStatus.BAD_REQUEST, "Выберите один из вариантов.") from error
                    if not 0 <= option_index < len(question.options):
                        raise WebRequestError(HTTPStatus.BAD_REQUEST, "Выберите один из вариантов.")
                    option = question.options[option_index]
                    saved_answer = str(option.id)
                    recorded_answer = option.option_text
                else:
                    recorded_answer = answer
                evaluator = AnswerEvaluationService(llm)
                if (
                    question.question_type is QuestionType.FORMULA
                    and evaluator.formula_comparator.compare(
                        saved_answer, question.reference_answer
                    ).reason
                    == "unsupported"
                ):
                    result = await llm.evaluate_answer(
                        question=question.question,
                        reference_answer=question.reference_answer,
                        key_points=question.key_points,
                        source_excerpt=question.source_excerpt,
                        user_answer=saved_answer,
                    )
                else:
                    result = await evaluator.evaluate(question, saved_answer)
                user = await UserRepository(session).get_or_create(
                    settings.admin_id, "website", "Web learner", True
                )
                quiz_session_id = body.get("session_id")
                quiz_session = None
                if quiz_session_id is not None:
                    try:
                        quiz_session_id = int(quiz_session_id)
                    except (ValueError, TypeError) as error:
                        raise WebRequestError(HTTPStatus.BAD_REQUEST, "Некорректная сессия квиза.") from error
                    quiz_session = await session.get(QuizSession, quiz_session_id)
                    if quiz_session is None or quiz_session.user_id != user.id or quiz_session.completed_at is not None:
                        raise WebRequestError(HTTPStatus.NOT_FOUND, "Сессия квиза недоступна.")
                    session_question = await session.scalar(
                        select(SessionQuestion).where(
                            SessionQuestion.quiz_session_id == quiz_session.id,
                            SessionQuestion.question_id == question.id,
                        )
                    )
                    if session_question is None:
                        raise WebRequestError(HTTPStatus.BAD_REQUEST, "Вопрос не входит в эту сессию.")
                    prior_attempt = await session.scalar(
                        select(Attempt).where(
                            Attempt.quiz_session_id == quiz_session.id,
                            Attempt.question_id == question.id,
                        ).order_by(Attempt.id.desc()).limit(1)
                    )
                    if prior_attempt is not None:
                        saved_result = prior_attempt.feedback or {}
                        return {
                            "verdict": prior_attempt.verdict.value,
                            "score": prior_attempt.score,
                            "short_explanation": saved_result.get("short_explanation", "Ответ уже был проверен."),
                            "reference_answer": question.reference_answer,
                            "explanation": question.explanation,
                            "source_excerpt": question.source_excerpt,
                            "knowledge_id": question.knowledge_element.external_id,
                            "theme_id": question.knowledge_element.external_id.split(".", 1)[0],
                            "progress_saved": True,
                            "duplicate_submission": True,
                        }
                    session_question.completed = True
                await ProgressService(session).record_attempt(
                    user_id=user.id,
                    question=question,
                    answer=recorded_answer,
                    verdict=result.verdict,
                    score=result.score,
                    feedback=result.model_dump(mode="json"),
                    hint_used=False,
                    answer_revealed=False,
                    quiz_session_id=quiz_session.id if quiz_session else None,
                )
                await session.commit()
                return {
                    "verdict": result.verdict.value,
                    "score": result.score,
                    "short_explanation": result.short_explanation,
                    "reference_answer": question.reference_answer,
                    "explanation": question.explanation,
                    "source_excerpt": question.source_excerpt,
                    "knowledge_id": question.knowledge_element.external_id,
                    "theme_id": question.knowledge_element.external_id.split(".", 1)[0],
                    "progress_saved": True,
                }
        finally:
            if isinstance(llm, OpenAiLlmClient):
                await llm.client.close()
            await engine.dispose()

    @staticmethod
    def _json_response(start_response, status: HTTPStatus, payload: dict[str, Any]) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return TheoryWebApplication._respond(start_response, status, body, "application/json; charset=utf-8")

    @staticmethod
    def _respond(start_response, status: HTTPStatus, body: bytes, content_type: str) -> list[bytes]:
        start_response(
            f"{status.value} {status.phrase}",
            [("Content-Type", content_type), ("Content-Length", str(len(body))), ("X-Content-Type-Options", "nosniff")],
        )
        return [body]
