"""Validate the checked-in theory repository before importing it into runtime storage."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.theory_data.models import KnowledgeDocument, QuestionDocument, SourceReference


class TheoryValidationError(ValueError):
    """A readable set of all repository validation errors."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class TheoryValidationReport:
    topic_directories: int
    knowledge_elements: int
    questions: int
    demo_directories: int


@dataclass(frozen=True)
class TheoryTopicDirectory:
    directory: Path
    knowledge: KnowledgeDocument
    questions: QuestionDocument


@dataclass(frozen=True)
class TheoryRepository:
    topics: tuple[TheoryTopicDirectory, ...]
    report: TheoryValidationReport


def _read_document(path: Path, model: type[KnowledgeDocument] | type[QuestionDocument]):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TheoryValidationError([f"{path}: invalid JSON: {exc}"]) from exc
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise TheoryValidationError([f"{path}: {error['msg']}" for error in exc.errors()]) from exc


def load_theory_repository(root: Path) -> TheoryRepository:
    """Load and validate all theory files before any database mutation begins."""
    if not root.is_dir():
        raise TheoryValidationError([f"Theory root does not exist: {root}"])

    directories = {path.parent for path in root.rglob("knowledge.json")}
    directories.update(path.parent for path in root.rglob("questions.json"))
    errors: list[str] = []
    total_knowledge = 0
    total_questions = 0
    demo_directories = 0
    known_ids: set[str] = set()
    question_ids: set[str] = set()
    source_references: dict[str, SourceReference] = {}
    topics: list[TheoryTopicDirectory] = []

    for directory in sorted(directories):
        knowledge_path = directory / "knowledge.json"
        questions_path = directory / "questions.json"
        if not knowledge_path.is_file() or not questions_path.is_file():
            errors.append(f"{directory}: requires both knowledge.json and questions.json")
            continue
        try:
            knowledge = _read_document(knowledge_path, KnowledgeDocument)
            questions = _read_document(questions_path, QuestionDocument)
        except TheoryValidationError as exc:
            errors.extend(exc.errors)
            continue

        taxonomy = (
            knowledge.section,
            knowledge.section_name,
            knowledge.topic,
            knowledge.topic_name,
            knowledge.subtopic,
            knowledge.subtopic_name,
            knowledge.is_demo,
        )
        question_taxonomy = (
            questions.section,
            questions.section_name,
            questions.topic,
            questions.topic_name,
            questions.subtopic,
            questions.subtopic_name,
            questions.is_demo,
        )
        if taxonomy != question_taxonomy:
            errors.append(f"{directory}: knowledge.json and questions.json have different taxonomy")
            continue
        if knowledge.is_demo:
            demo_directories += 1

        document_knowledge_ids = {item.id for item in knowledge.knowledge}
        duplicate_knowledge_ids = known_ids & document_knowledge_ids
        if duplicate_knowledge_ids:
            errors.append(
                f"{directory}: duplicate knowledge IDs: {sorted(duplicate_knowledge_ids)}"
            )
        known_ids.update(document_knowledge_ids)

        for question in questions.questions:
            if question.knowledge_id not in document_knowledge_ids:
                errors.append(
                    f"{questions_path}: question {question.id} references unknown "
                    f"knowledge_id {question.knowledge_id}"
                )
            if question.id in question_ids:
                errors.append(f"{questions_path}: duplicate question ID: {question.id}")
            question_ids.add(question.id)

        for source in [
            *(item.source for item in knowledge.knowledge),
            *(item.source for item in questions.questions),
        ]:
            previous = source_references.setdefault(source.id, source)
            if previous != source:
                errors.append(f"{directory}: source ID {source.id} has conflicting metadata")

        total_knowledge += len(knowledge.knowledge)
        total_questions += len(questions.questions)
        topics.append(
            TheoryTopicDirectory(directory=directory, knowledge=knowledge, questions=questions)
        )

    if errors:
        raise TheoryValidationError(errors)
    return TheoryRepository(
        topics=tuple(topics),
        report=TheoryValidationReport(
            topic_directories=len(directories),
            knowledge_elements=total_knowledge,
            questions=total_questions,
            demo_directories=demo_directories,
        ),
    )


def validate_theory_repository(root: Path) -> TheoryValidationReport:
    """Validate paired files without importing or mutating the database."""
    return load_theory_repository(root).report
