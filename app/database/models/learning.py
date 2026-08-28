from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.enums import AttemptVerdict, QuizMode
from app.database.base import Base, CreatedAtMixin


class QuizSession(CreatedAtMixin, Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[QuizMode] = mapped_column(Enum(QuizMode, native_enum=False), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="all", nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionQuestion(Base):
    __tablename__ = "session_questions"
    __table_args__ = (UniqueConstraint("quiz_session_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Attempt(CreatedAtMixin, Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    quiz_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="SET NULL")
    )
    answer: Mapped[str] = mapped_column(Text)
    verdict: Mapped[AttemptVerdict] = mapped_column(
        Enum(AttemptVerdict, native_enum=False), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answer_revealed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Progress(CreatedAtMixin, Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "knowledge_element_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_element_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_elements.id", ondelete="CASCADE"), index=True
    )
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewSchedule(CreatedAtMixin, Base):
    __tablename__ = "review_schedule"
    __table_args__ = (UniqueConstraint("user_id", "knowledge_element_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_element_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_elements.id", ondelete="CASCADE"), index=True
    )
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
