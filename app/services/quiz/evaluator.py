from app.core.enums import AttemptVerdict, QuestionType
from app.database.models.content import Question
from app.schemas.evaluation import EvaluationResult
from app.services.llm.client import LlmClient
from app.services.quiz.formula import FormulaComparator


class AnswerEvaluationService:
    def __init__(self, llm: LlmClient, formula_comparator: FormulaComparator | None = None) -> None:
        self.llm = llm
        self.formula_comparator = formula_comparator or FormulaComparator()

    async def evaluate(self, question: Question, user_answer: str) -> EvaluationResult:
        if question.question_type is QuestionType.MULTIPLE_CHOICE:
            correct = any(
                option.is_correct and user_answer.strip() == str(option.id)
                for option in question.options
            )
            return EvaluationResult(
                verdict=AttemptVerdict.CORRECT if correct else AttemptVerdict.INCORRECT,
                score=1.0 if correct else 0.0,
                short_explanation="Верно." if correct else "Неверно. Попробуй ещё раз.",
            )
        if question.question_type is QuestionType.FORMULA:
            result = self.formula_comparator.compare(user_answer, question.reference_answer)
            if result.equivalent:
                return EvaluationResult(
                    verdict=AttemptVerdict.CORRECT, score=1.0, short_explanation="Формула верна."
                )
            return EvaluationResult(
                verdict=AttemptVerdict.INCORRECT,
                score=0.0,
                what_is_wrong=["Форма записи не эквивалентна эталонной."],
                short_explanation="Неверно. Попробуй ещё раз.",
            )
        return await self.llm.evaluate_answer(
            question=question.question,
            reference_answer=question.reference_answer,
            key_points=question.key_points,
            source_excerpt=question.source_excerpt,
            user_answer=user_answer,
        )
