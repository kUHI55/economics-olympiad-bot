from enum import StrEnum


class KnowledgeType(StrEnum):
    DEFINITION = "definition"
    FORMULA = "formula"
    NOTATION = "notation"
    MECHANISM = "mechanism"
    CAUSAL_RELATIONSHIP = "causal_relationship"
    COMPARISON = "comparison"
    EXAMPLE = "example"
    GRAPHICAL_CONCEPT = "graphical_concept"
    COMMON_MISTAKE = "common_mistake"
    TERM = "term"


class QuestionType(StrEnum):
    FORMULA = "formula"
    DEFINITION = "definition"
    NOTATION = "notation"
    UNDERSTANDING = "understanding"
    CAUSAL_RELATIONSHIP = "causal_relationship"
    COMPARISON = "comparison"
    COMMON_MISTAKE = "common_mistake"
    MULTIPLE_CHOICE = "multiple_choice"


class AttemptVerdict(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"


class QuizMode(StrEnum):
    PRACTICE = "practice"
    BLITZ = "blitz"
    EXAM = "exam"
    REVIEW = "review"
    WEAK_AREAS = "weak_areas"


class SourceType(StrEnum):
    TEXT = "text"
    TXT = "txt"
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
