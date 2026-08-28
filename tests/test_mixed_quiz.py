import unittest
from types import SimpleNamespace

from app.core.enums import QuestionType, QuizMode
from app.services.quiz.service import QuizService


class MixedQuizSelectionTests(unittest.TestCase):
    def test_mixed_mode_uses_requested_distribution_when_available(self) -> None:
        quotas = {
            QuestionType.FORMULA: 4,
            QuestionType.DEFINITION: 4,
            QuestionType.UNDERSTANDING: 6,
            QuestionType.CAUSAL_RELATIONSHIP: 3,
            QuestionType.MULTIPLE_CHOICE: 3,
        }
        candidates = []
        question_id = 1
        for question_type, amount in quotas.items():
            for _ in range(amount):
                candidates.append(SimpleNamespace(id=question_id, question_type=question_type))
                question_id += 1
        selected = QuizService._select_questions(candidates, QuizMode.PRACTICE, None, 20)
        actual = {question_type: 0 for question_type in quotas}
        for question in selected:
            actual[question.question_type] += 1
        self.assertEqual(actual, quotas)
