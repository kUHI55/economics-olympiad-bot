import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.theory_data.validator import TheoryValidationError, validate_theory_repository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = PROJECT_ROOT / "data" / "theory"


class TheoryDataValidatorTests(unittest.TestCase):
    def test_validates_demo_topic(self) -> None:
        report = validate_theory_repository(DEMO_ROOT)
        self.assertEqual(report.topic_directories, 1)
        self.assertEqual(report.knowledge_elements, 1)
        self.assertEqual(report.questions, 1)
        self.assertEqual(report.demo_directories, 1)

    def test_rejects_question_with_unknown_knowledge_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "theory"
            fixture_directory = root / "demo" / "validation-fixture"
            fixture_directory.mkdir(parents=True)
            for name in ("knowledge.json", "questions.json"):
                shutil.copy(
                    DEMO_ROOT / "demo" / "validation-fixture" / name, fixture_directory / name
                )
            questions_path = fixture_directory / "questions.json"
            payload = json.loads(questions_path.read_text(encoding="utf-8"))
            payload["questions"][0]["knowledge_id"] = "demo.validation-fixture.unknown"
            questions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(TheoryValidationError, "unknown knowledge_id"):
                validate_theory_repository(root)

    def test_rejects_multiple_choice_without_matching_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "theory"
            fixture_directory = root / "demo" / "validation-fixture"
            fixture_directory.mkdir(parents=True)
            for name in ("knowledge.json", "questions.json"):
                shutil.copy(
                    DEMO_ROOT / "demo" / "validation-fixture" / name, fixture_directory / name
                )
            questions_path = fixture_directory / "questions.json"
            payload = json.loads(questions_path.read_text(encoding="utf-8"))
            payload["questions"][0]["correct_answer"] = "Z"
            questions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(TheoryValidationError, "correct_answer"):
                validate_theory_repository(root)
