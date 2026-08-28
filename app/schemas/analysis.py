from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import KnowledgeType, QuestionType, SourceType


class KnowledgeElementDraft(BaseModel):
    """A proposed item. All assertions must be covered by ``source_excerpt``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=2, max_length=255)
    knowledge_type: KnowledgeType
    content: str = Field(min_length=2)
    source_excerpt: str = Field(min_length=5)
    formula: str | None = None
    notation: dict[str, str] | None = None
    economic_meaning: str | None = None


class QuestionOptionDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1)
    is_correct: bool = False


class QuestionDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    knowledge_element_index: int = Field(ge=0)
    question: str = Field(min_length=5)
    question_type: QuestionType
    difficulty: int = Field(default=2, ge=1, le=5)
    reference_answer: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    hint: str = Field(min_length=2)
    explanation: str = Field(min_length=2)
    source_excerpt: str = Field(min_length=5)
    options: list[QuestionOptionDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_options(self) -> "QuestionDraft":
        if self.question_type is QuestionType.MULTIPLE_CHOICE:
            if not 2 <= len(self.options) <= 6:
                raise ValueError("Multiple choice needs from 2 to 6 options")
            if sum(option.is_correct for option in self.options) != 1:
                raise ValueError("Multiple choice needs exactly one correct option")
        elif self.options:
            raise ValueError("Options are allowed only for multiple choice questions")
        return self


class MaterialAnalysis(BaseModel):
    """LLM output reviewed by the administrator before it becomes data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_name: str = Field(min_length=1)
    source_type: SourceType
    source_date: date | None = None
    knowledge_elements: list[KnowledgeElementDraft] = Field(default_factory=list)
    questions: list[QuestionDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("questions")
    @classmethod
    def element_index_exists(cls, value: list[QuestionDraft], info) -> list[QuestionDraft]:
        elements = info.data.get("knowledge_elements", [])
        for question in value:
            if question.knowledge_element_index >= len(elements):
                raise ValueError("Question refers to a missing knowledge element")
        return value

    def counts(self) -> dict[str, int]:
        return {
            "elements": len(self.knowledge_elements),
            "definitions": sum(
                e.knowledge_type is KnowledgeType.DEFINITION for e in self.knowledge_elements
            ),
            "formulas": sum(
                e.knowledge_type is KnowledgeType.FORMULA for e in self.knowledge_elements
            ),
            "mechanisms": sum(
                e.knowledge_type is KnowledgeType.MECHANISM for e in self.knowledge_elements
            ),
            "questions": len(self.questions),
            "common_mistakes": sum(
                e.knowledge_type is KnowledgeType.COMMON_MISTAKE for e in self.knowledge_elements
            ),
        }
