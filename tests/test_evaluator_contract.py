import unittest

from app.services.quiz.evaluator_contract import validate_evaluation_payload


class EvaluatorContractTests(unittest.TestCase):
    def test_valid_payload(self) -> None:
        payload = {
            "verdict": "partial",
            "score": 0.5,
            "what_is_correct": ["Названа ставка."],
            "what_is_wrong": [],
            "missing_points": ["Нет причинной связи."],
            "short_explanation": "Уточни механизм.",
        }
        self.assertEqual(validate_evaluation_payload(payload), [])

    def test_rejects_invalid_verdict_and_score(self) -> None:
        issues = validate_evaluation_payload({"verdict": "maybe", "score": 2})
        self.assertIn("Invalid verdict", issues)
        self.assertIn("Score must be between 0 and 1", issues)
