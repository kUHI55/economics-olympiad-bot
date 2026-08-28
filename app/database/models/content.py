from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import KnowledgeType, QuestionType, SourceType
from app.database.base import Base, CreatedAtMixin


class MaterialDraft(CreatedAtMixin, Base):
    """Unconfirmed material and the LLM proposal; it never enters the knowledge base automatically."""

    __tablename__ = "material_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"))
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    subtopic_id: Mapped[int | None] = mapped_column(ForeignKey("subtopics.id", ondelete="SET NULL"))
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    source_date: Mapped[date | None] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Source(CreatedAtMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"))
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    subtopic_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtopics.id", ondelete="SET NULL"), index=True
    )
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    source_date: Mapped[date | None] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(1024))

    knowledge_elements: Mapped[list["KnowledgeElement"]] = relationship(back_populates="source")


class KnowledgeElement(CreatedAtMixin, Base):
    __tablename__ = "knowledge_elements"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="SET NULL"), index=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    subtopic_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtopics.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    knowledge_type: Mapped[KnowledgeType] = mapped_column(
        Enum(KnowledgeType, native_enum=False), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    formula: Mapped[str | None] = mapped_column(String(1000))
    notation: Mapped[dict[str, str] | None] = mapped_column(JSON)
    economic_meaning: Mapped[str | None] = mapped_column(Text)
    source_excerpt: Mapped[str] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="knowledge_elements")
    questions: Mapped[list["Question"]] = relationship(back_populates="knowledge_element")


class Question(CreatedAtMixin, Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_element_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_elements.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False), index=True
    )
    difficulty: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    hint: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    source_excerpt: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    knowledge_element: Mapped[KnowledgeElement] = relationship(back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="QuestionOption.position"
    )


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    option_text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    question: Mapped[Question] = relationship(back_populates="options")
