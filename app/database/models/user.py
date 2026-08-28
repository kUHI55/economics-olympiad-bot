from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False)


class UserSettings(CreatedAtMixin, Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_hour: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Yekaterinburg", nullable=False)
    last_reminder_date: Mapped[date | None] = mapped_column(Date)

    user: Mapped[User] = relationship(back_populates="settings")
