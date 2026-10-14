"""Ephemeral theory documents shared by validator and importer tests."""

import json
from pathlib import Path

KNOWLEDGE_ID = "test-fixture.validation-fixture.sample-term"
QUESTION_ID = "test-fixture.validation-fixture.sample-term-check"
SOURCE_EXCERPT = "A temporary fixture used only to test theory file handling."


def write_theory_fixture(directory: Path) -> tuple[Path, Path]:
    """Write one valid demo knowledge/question pair into a temporary directory."""
    directory.mkdir(parents=True, exist_ok=True)
    taxonomy = {
        "schema_version": 1,
        "section": "test-fixture",
        "topic": "validation-fixture",
        "subtopic": "example",
        "is_demo": True,
    }
    source = {
        "id": "test-fixture.validation-fixture.source",
        "name": "Temporary test fixture",
        "source_type": "text",
        "excerpt": SOURCE_EXCERPT,
    }
    knowledge_path = directory / "knowledge.json"
    knowledge_path.write_text(
        json.dumps(
            {
                **taxonomy,
                "knowledge": [
                    {
                        "id": KNOWLEDGE_ID,
                        "title": "Fixture term",
                        "type": "term",
                        "explanation": "A temporary element for exercising validation.",
                        "source": source,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    questions_path = directory / "questions.json"
    questions_path.write_text(
        json.dumps(
            {
                **taxonomy,
                "questions": [
                    {
                        "id": QUESTION_ID,
                        "knowledge_id": KNOWLEDGE_ID,
                        "type": "multiple_choice",
                        "difficulty": 1,
                        "question": "What is this temporary fixture for?",
                        "options": [
                            {"id": "A", "text": "Checking theory file handling"},
                            {"id": "B", "text": "Teaching economics"},
                        ],
                        "correct_answer": "A",
                        "reference_answer": "Checking theory file handling.",
                        "key_points": ["fixture", "file handling"],
                        "explanation": "This is test-only data, not educational content.",
                        "source": source,
                        "source_excerpt": SOURCE_EXCERPT,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return knowledge_path, questions_path
