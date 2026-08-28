import unittest

from pydantic import ValidationError

from app.core.enums import AttemptVerdict
from app.schemas.evaluation import EvaluationResult


class EvaluatorSchemaTests(unittest.TestCase):
    def test_schema_accepts_uncertain_response(self) -> None:
        result = EvaluationResult(verdict=AttemptVerdict.UNCERTAIN, score=0.5)
        self.assertEqual(result.verdict, AttemptVerdict.UNCERTAIN)

    def test_schema_rejects_inconsistent_correct_score(self) -> None:
        with self.assertRaises(ValidationError):
            EvaluationResult(verdict=AttemptVerdict.CORRECT, score=0.4)
