from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin


class Section(CreatedAtMixin, Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class Topic(CreatedAtMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("section_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    section: Mapped[Section] = relationship(back_populates="topics")
    subtopics: Mapped[list["Subtopic"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class Subtopic(CreatedAtMixin, Base):
    __tablename__ = "subtopics"
    __table_args__ = (UniqueConstraint("topic_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    topic: Mapped[Topic] = relationship(back_populates="subtopics")
