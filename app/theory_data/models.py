from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import KnowledgeType, QuestionType, SourceType

ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
OPTION_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class TheoryFileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceReference(TheoryFileModel):
    id: str = Field(pattern=ID_PATTERN, min_length=2, max_length=128)
    name: str = Field(min_length=2, max_length=255)
    source_type: SourceType
    source_date: date | None = None
    excerpt: str = Field(min_length=5)


class KnowledgeItem(TheoryFileModel):
    id: str = Field(pattern=ID_PATTERN, min_length=2, max_length=160)
    title: str = Field(min_length=2, max_length=255)
    type: KnowledgeType
    formula: str | None = Field(default=None, max_length=1000)
    definitions: dict[str, str] = Field(default_factory=dict)
    explanation: str = Field(min_length=2)
    source: SourceReference


class KnowledgeDocument(TheoryFileModel):
    schema_version: Literal[1] = 1
    section: str = Field(pattern=ID_PATTERN, min_length=2, max_length=64)
    topic: str = Field(pattern=ID_PATTERN, min_length=2, max_length=64)
    subtopic: str | None = Field(default=None, pattern=ID_PATTERN, max_length=64)
    is_demo: bool = False
    knowledge: list[KnowledgeItem] = Field(min_length=1)

    @model_validator(mode="after")
    def knowledge_ids_are_unique(self) -> "KnowledgeDocument":
        ids = [item.id for item in self.knowledge]
        if len(ids) != len(set(ids)):
            raise ValueError("Knowledge IDs must be unique within a file")
        return self


class QuestionOption(TheoryFileModel):
    id: str = Field(pattern=OPTION_ID_PATTERN, min_length=1, max_length=32)
    text: str = Field(min_length=1)


class QuestionItem(TheoryFileModel):
    id: str = Field(pattern=ID_PATTERN, min_length=2, max_length=160)
    knowledge_id: str = Field(pattern=ID_PATTERN, min_length=2, max_length=160)
    type: QuestionType
    difficulty: int = Field(ge=1, le=5)
    question: str = Field(min_length=5)
    options: list[QuestionOption] = Field(default_factory=list)
    correct_answer: str | None = None
    reference_answer: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=2)
    source: SourceReference
    source_excerpt: str = Field(min_length=5)

    @model_validator(mode="after")
    def validate_answer_format(self) -> "QuestionItem":
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Option IDs must be unique")
        if self.type is QuestionType.MULTIPLE_CHOICE:
            if not 2 <= len(self.options) <= 6:
                raise ValueError("Multiple choice needs from 2 to 6 options")
            if self.correct_answer not in option_ids:
                raise ValueError("Multiple choice correct_answer must reference one option ID")
        elif self.options or self.correct_answer is not None:
            raise ValueError("Only multiple choice questions may have options or correct_answer")
        if self.source_excerpt != self.source.excerpt:
            raise ValueError("source_excerpt must exactly match source.excerpt")
        return self


class QuestionDocument(TheoryFileModel):
    schema_version: Literal[1] = 1
    section: str = Field(pattern=ID_PATTERN, min_length=2, max_length=64)
    topic: str = Field(pattern=ID_PATTERN, min_length=2, max_length=64)
    subtopic: str | None = Field(default=None, pattern=ID_PATTERN, max_length=64)
    is_demo: bool = False
    questions: list[QuestionItem] = Field(min_length=1)

    @model_validator(mode="after")
    def question_ids_are_unique(self) -> "QuestionDocument":
        ids = [item.id for item in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique within a file")
        return self
