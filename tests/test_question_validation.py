import unittest

from app.core.enums import QuestionType
from app.services.quiz.validation import validate_question


class QuestionValidationTests(unittest.TestCase):
    def test_multiple_choice_requires_exactly_one_correct_option(self) -> None:
        issues = validate_question(
            question="Что изменится при росте ставки?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            reference_answer="Цена снизится",
            source_excerpt="При росте ставки цена облигации снижается.",
            options=["Вырастет", "Снизится"],
            correct_option_indexes=[0, 1],
        )
        self.assertTrue(any(issue.field == "correct_option" for issue in issues))

    def test_free_answer_does_not_accept_options(self) -> None:
        issues = validate_question(
            question="Что такое рабочая сила?",
            question_type=QuestionType.DEFINITION,
            reference_answer="Занятые и безработные.",
            source_excerpt="Рабочая сила включает занятых и безработных.",
            options=["A", "B"],
            correct_option_indexes=[0],
        )
        self.assertTrue(any(issue.field == "options" for issue in issues))
