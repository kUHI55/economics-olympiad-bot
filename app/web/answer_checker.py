"""Conservative answer checking for the local, file-backed study mode."""

import re
import unicodedata

from app.core.enums import AttemptVerdict, QuestionType
from app.services.quiz.formula import FormulaComparator
from app.theory_data.models import QuestionItem


def _normalise_prose(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE)


def _normalise_formula_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.strip().rstrip(".; ").split())


def check_local_answer(question: QuestionItem, answer: str) -> dict[str, object]:
    """Return an evidence-based verdict without persisting progress or guessing."""
    verdict = AttemptVerdict.UNCERTAIN
    score: float | None = None
    explanation = "Не удалось надёжно оценить ответ автоматически."

    if question.type is QuestionType.MULTIPLE_CHOICE:
        try:
            option_index = int(answer)
        except ValueError as error:
            raise ValueError("Выберите один из вариантов ответа.") from error
        if not 0 <= option_index < len(question.options):
            raise ValueError("Выберите один из вариантов ответа.")
        selected = question.options[option_index]
        is_correct = selected.id == question.correct_answer
        verdict = AttemptVerdict.CORRECT if is_correct else AttemptVerdict.INCORRECT
        score = 1.0 if is_correct else 0.0
        explanation = "Верно." if is_correct else "Неверно. Правильный ответ указан ниже."
    elif question.type is QuestionType.FORMULA:
        if _normalise_formula_text(answer) == _normalise_formula_text(question.reference_answer):
            verdict = AttemptVerdict.CORRECT
            score = 1.0
            explanation = "Формула совпадает с эталонной записью."
        else:
            comparison = FormulaComparator().compare(answer, question.reference_answer)
            if comparison.equivalent:
                verdict = AttemptVerdict.CORRECT
                score = 1.0
                explanation = "Формула эквивалентна эталонной."
            elif comparison.reason == "different":
                verdict = AttemptVerdict.INCORRECT
                score = 0.0
                explanation = "Формула отличается от эталонной."

    else:
        answer_text = _normalise_prose(answer)
        expected_text = _normalise_prose(question.reference_answer)
        if answer_text == expected_text:
            verdict = AttemptVerdict.CORRECT
            score = 1.0
            explanation = "Ответ совпадает с эталонным по тексту."

    return {
        "verdict": verdict.value,
        "score": score,
        "short_explanation": explanation,
        "reference_answer": question.reference_answer,
        "explanation": question.explanation,
        "source_excerpt": question.source_excerpt,
        "knowledge_id": question.knowledge_id,
        "theme_id": question.knowledge_id.split(".", 1)[0],
        "progress_saved": False,
    }
