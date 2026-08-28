from dataclasses import dataclass

from app.core.enums import QuestionType


@dataclass(frozen=True)
class QuestionValidationIssue:
    field: str
    message: str


def validate_question(
    *,
    question: str,
    question_type: QuestionType,
    reference_answer: str,
    source_excerpt: str,
    options: list[str] | None = None,
    correct_option_indexes: list[int] | None = None,
) -> list[QuestionValidationIssue]:
    """Rules applied before a generated question can be proposed for saving."""
    issues: list[QuestionValidationIssue] = []
    if len(question.strip()) < 5:
        issues.append(QuestionValidationIssue("question", "Вопрос слишком короткий."))
    if not reference_answer.strip():
        issues.append(QuestionValidationIssue("reference_answer", "Нет эталонного ответа."))
    if len(source_excerpt.strip()) < 5:
        issues.append(QuestionValidationIssue("source_excerpt", "Нет фрагмента источника."))
    options = options or []
    correct_option_indexes = correct_option_indexes or []
    if question_type is QuestionType.MULTIPLE_CHOICE:
        if not 2 <= len(options) <= 6:
            issues.append(QuestionValidationIssue("options", "Нужно от 2 до 6 вариантов."))
        if len({option.casefold().strip() for option in options}) != len(options):
            issues.append(QuestionValidationIssue("options", "Варианты ответа повторяются."))
        if len(correct_option_indexes) != 1:
            issues.append(
                QuestionValidationIssue("correct_option", "Нужен ровно один правильный вариант.")
            )
        elif not 0 <= correct_option_indexes[0] < len(options):
            issues.append(
                QuestionValidationIssue("correct_option", "Правильный вариант вне списка.")
            )
    elif options or correct_option_indexes:
        issues.append(
            QuestionValidationIssue("options", "Варианты допустимы только в тестовом вопросе.")
        )
    return issues
