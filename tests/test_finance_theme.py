import json
import re
import unittest
from pathlib import Path

from app.theory_data.validator import load_theory_repository
from app.web.application import TheoryWebApplication
from tests.test_web import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINANCE_ROOT = PROJECT_ROOT / "data" / "theory" / "finance"


class FinanceThemeTests(unittest.TestCase):
    def test_source_inventory_is_fully_structured_and_linked(self) -> None:
        repository = load_theory_repository(PROJECT_ROOT / "data" / "theory")
        finance = [topic for topic in repository.topics if topic.knowledge.section == "finance"]
        self.assertEqual(len(finance), 13)

        knowledge = [item for topic in finance for item in topic.knowledge.knowledge]
        questions = [item for topic in finance for item in topic.questions.questions]
        knowledge_by_id = {item.id: item for item in knowledge}
        self.assertEqual(len(knowledge), 363)
        self.assertEqual(len(questions), 362)
        self.assertEqual(len(knowledge_by_id), len(knowledge))
        ids = set(knowledge_by_id)
        self.assertEqual(sum(identifier.startswith("finance.definition.") for identifier in ids), 96)
        self.assertEqual(sum(identifier.startswith("finance.formula.") for identifier in ids), 83)
        self.assertEqual(sum(identifier.startswith("finance.construction.") for identifier in ids), 120)
        self.assertEqual(sum(identifier.startswith("finance.error.") for identifier in ids), 30)
        self.assertEqual(sum(identifier.startswith("finance.signal.") for identifier in ids), 27)
        self.assertEqual(sum(identifier.startswith("finance.discrepancy.") for identifier in ids), 4)

        for question in questions:
            with self.subTest(question_id=question.id):
                self.assertIn(question.knowledge_id, knowledge_by_id)
                self.assertEqual(len(question.options), 4)
                choices = [option.text.strip().casefold() for option in question.options]
                self.assertTrue(all(choices))
                self.assertEqual(len(set(choices)), 4)
                right = [option for option in question.options if option.id == question.correct_answer]
                self.assertEqual(len(right), 1)
                self.assertEqual(right[0].text, question.reference_answer)
                self.assertTrue(question.explanation.strip())

    def test_all_120_construction_cards_and_required_discrepancies_are_present(self) -> None:
        catalog = (FINANCE_ROOT / "problem-constructions.md").read_text(encoding="utf-8")
        card_ids = re.findall(r"^### К(\d{2,3})\.", catalog, re.MULTILINE)
        self.assertEqual(card_ids, [f"{number:02d}" for number in range(1, 121)])

        construction_items = {
            item["id"]
            for path in FINANCE_ROOT.rglob("knowledge.json")
            for item in json.loads(path.read_text(encoding="utf-8"))["knowledge"]
            if item["id"].startswith("finance.construction.")
        }
        self.assertEqual(construction_items, {f"finance.construction.k{number:03d}" for number in range(1, 121)})

        notes = (FINANCE_ROOT / "study-notes.md").read_text(encoding="utf-8")
        knowledge_blob = "\n".join(
            json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
            for path in FINANCE_ROOT.rglob("knowledge.json")
        )
        for marker in ("Задача4(в)", "Задача18", "Задача24", "Задача38(д)"):
            with self.subTest(discrepancy=marker):
                self.assertIn(marker, notes)
                self.assertIn(marker, knowledge_blob)
        self.assertIn("79,1667%", notes)
        self.assertIn("13946,67", notes)
        self.assertIn("13280", notes)

        repository = load_theory_repository(PROJECT_ROOT / "data" / "theory")
        finance = [topic for topic in repository.topics if topic.knowledge.section == "finance"]
        finance_questions = [item for topic in finance for item in topic.questions.questions]
        question_ids = {item.id for item in finance_questions}
        self.assertTrue(
            {f"finance.error.e{number:02d}.question" for number in range(1, 31)}
            <= question_ids
        )
        self.assertIn("finance.method.protocol-10.question", question_ids)
        self.assertIn("finance.method.protocol-12.question", question_ids)

    def test_finance_questions_have_no_unfilled_templates_and_formula_prompts_use_linked_knowledge(self) -> None:
        repository = load_theory_repository(PROJECT_ROOT / "data" / "theory")
        finance = [topic for topic in repository.topics if topic.knowledge.section == "finance"]
        questions = [question for topic in finance for question in topic.questions.questions]
        knowledge = {
            item.id: item
            for topic in finance
            for item in topic.knowledge.knowledge
        }
        placeholders = re.compile(
            r"\[(?:[^\]]*(?:формул\w*|ответ\w*|заполн\w*|placeholder|todo)[^\]]*)\]"
            r"|\b(?:TODO|TBD|PLACEHOLDER)\b",
            re.IGNORECASE,
        )
        for question in questions:
            with self.subTest(question_id=question.id):
                self.assertIsNone(placeholders.search(question.question))

        formula_questions = [question for question in questions if question.id.startswith("finance.formula.")]
        self.assertEqual(len(formula_questions), 83)
        for question in formula_questions:
            item = knowledge[question.knowledge_id]
            if item.formula:
                self.assertIn(f"`{item.formula}`", question.question)
            else:
                self.assertIn(item.explanation, question.question)

    def test_review_sheet_and_documents_are_served_by_the_existing_site(self) -> None:
        review = (FINANCE_ROOT / "review-sheet.md").read_text(encoding="utf-8")
        self.assertIn("Задача 38(д)", review)
        self.assertIn("Maximin", review)
        self.assertIn("IRR", review)

        application = TheoryWebApplication()
        catalog = json.loads(request(application, "/api/theory")["body"])
        finance = next(theme for theme in catalog["themes"] if theme["id"] == "finance")
        self.assertEqual(finance["title"], "Финансы")
        self.assertEqual(finance["question_count"], 362)
        self.assertEqual(finance["knowledge_count"], 363)
        self.assertEqual(len(finance["subtopics"]), 13)
        self.assertEqual(
            set(finance["documents"]),
            {"study-notes.md", "problem-constructions.md", "review-sheet.md"},
        )
        api_questions = [
            question
            for topic in finance["subtopics"]
            for question in topic["questions"]
            if question["id"].startswith("finance.formula.")
        ]
        self.assertEqual(len(api_questions), 83)
        self.assertTrue(all("[формула из справочника]" not in item["question"] for item in api_questions))
        expected_prompts = {
            item["id"]: item["question"]
            for item in json.loads(
                (FINANCE_ROOT / "00-definitions-and-formulas" / "questions.json").read_text(
                    encoding="utf-8"
                )
            )["questions"]
            if item["id"].startswith("finance.formula.")
        }
        self.assertEqual(
            {item["id"]: item["question"] for item in api_questions},
            expected_prompts,
        )
        self.assertTrue(
            all("correct_answer" not in item and "reference_answer" not in item for item in api_questions)
        )

        for document in finance["documents"]:
            with self.subTest(document=document):
                response = request(application, f"/api/documents/finance/{document}")
                self.assertTrue(response["status"].startswith("200"))
                self.assertEqual(response["headers"]["Content-Type"], "text/markdown; charset=utf-8")
                self.assertEqual(response["body"], (FINANCE_ROOT / document).read_bytes())
