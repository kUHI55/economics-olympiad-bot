import hashlib
import json
import unittest

from app.theory_data.validator import load_theory_repository
from app.web.application import THEORY_ROOT, TheoryWebApplication


class AddedThemesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = load_theory_repository(THEORY_ROOT)
        cls.web = TheoryWebApplication(THEORY_ROOT)

    def test_added_topics_preserve_source_record_counts_and_open_question_formats(self) -> None:
        by_section = {}
        for topic in self.repository.topics:
            by_section.setdefault(topic.knowledge.section, []).append(topic)

        for section, expected_knowledge, expected_questions in (
            ("financial-literacy", 53, 71),
            ("elasticity", 60, 62),
        ):
            with self.subTest(section=section):
                topics = by_section[section]
                knowledge = [item for topic in topics for item in topic.knowledge.knowledge]
                questions = [item for topic in topics for item in topic.questions.questions]
                self.assertEqual(len(knowledge), expected_knowledge)
                self.assertEqual(len(questions), expected_questions)
                self.assertTrue(all(item.source_record_id for item in knowledge))
                self.assertTrue(all(item.source_record_id for item in questions))
                self.assertTrue(all(not item.options and item.correct_answer is None for item in questions))
                self.assertTrue(all(item.source_type for item in questions))
                self.assertTrue(all(item.source_slides for item in questions))

                knowledge_ids = {item.id for item in knowledge}
                source_ids = {item.source_record_id for item in knowledge}
                self.assertEqual(len(knowledge_ids), len(knowledge))
                self.assertEqual(len(source_ids), len(knowledge))
                for question in questions:
                    with self.subTest(question=question.source_record_id):
                        self.assertTrue(question.linked_knowledge_ids)
                        self.assertIn(question.knowledge_id, question.linked_knowledge_ids)
                        self.assertTrue(set(question.linked_knowledge_ids) <= knowledge_ids)

    def test_source_notes_are_complete_and_formula_records_keep_latex_metadata(self) -> None:
        expected = {
            "financial-literacy": ("Финансовая грамотность", "97a26e88547799e0b16fda3302c82bb603f8c5779b71d07f5fa26b55817c876a"),
            "elasticity": ("Эластичность", "732e98b76e1276709ff06af48c54e060411bc2a195c1bd146edc32230415cdc5"),
        }
        for section, (expected_heading, expected_hash) in expected.items():
            note = (THEORY_ROOT / section / "study-notes.md").read_text(encoding="utf-8")
            self.assertIn(expected_heading, note)
            self.assertIn("Контрольный список покрытия слайдов", note)
            self.assertEqual(hashlib.sha256(note.encode("utf-8")).hexdigest(), expected_hash)

        formulas = [
            item
            for topic in self.repository.topics
            if topic.knowledge.section in {"financial-literacy", "elasticity"}
            for item in topic.knowledge.knowledge
            if item.formula
        ]
        self.assertEqual(len(formulas), 51)
        for item in formulas:
            self.assertTrue(item.formula.strip())
            self.assertTrue(item.definitions)
            self.assertTrue(item.economic_meaning)
            self.assertTrue(item.conditions)
            self.assertIsNotNone(item.notes)
            self.assertTrue(item.source_slides)

    def test_theory_api_exposes_theme_formulas_and_links_without_answer_keys(self) -> None:
        payload = self.web._theory_payload()
        themes = {theme["id"]: theme for theme in payload["themes"]}
        for theme_id in ("financial-literacy", "elasticity"):
            with self.subTest(theme=theme_id):
                theme = themes[theme_id]
                self.assertGreater(len(theme["subtopics"]), 1)
                self.assertTrue(theme["documents"] and "study-notes.md" in theme["documents"])
                self.assertTrue(theme["description"])
                questions = [q for subtopic in theme["subtopics"] for q in subtopic["questions"]]
                self.assertTrue(questions)
                self.assertTrue(all(q["related_knowledge"] for q in questions))
                self.assertTrue(all("reference_answer" not in q and "correct_answer" not in q for q in questions))
                knowledge = [item for subtopic in theme["subtopics"] for item in subtopic["knowledge"]]
                self.assertTrue(any(item.get("formula") for item in knowledge))
                self.assertTrue(all("economic_meaning" in item for item in knowledge if item.get("formula")))

    def test_source_mapping_keeps_original_ids_and_counts(self) -> None:
        for section, expected in (("financial-literacy", (38, 15, 71)), ("elasticity", (24, 36, 62))):
            mapping = json.loads((THEORY_ROOT / section / "source-mapping.json").read_text(encoding="utf-8"))
            actual = tuple(len(mapping["id_mapping"][kind]) for kind in ("concepts", "formulas", "questions"))
            self.assertEqual(actual, expected)
