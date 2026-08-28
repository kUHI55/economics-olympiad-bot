import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.models.learning import ReviewSchedule
from app.database.models.user import User, UserSettings


class ReminderService:
    """Small in-process scheduler. One bot container is intentional for this personal MVP."""

    def __init__(self, session_factory: async_sessionmaker, default_timezone: str) -> None:
        self.session_factory = session_factory
        self.default_timezone = default_timezone

    async def run(self, bot: Bot, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self.send_due_reminders(bot)
            except Exception:
                # Polling must not stop because one recipient or database query failed.
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except TimeoutError:
                continue

    async def send_due_reminders(self, bot: Bot) -> None:
        now_utc = datetime.now(UTC)
        async with self.session_factory() as session:
            settings_rows = await session.execute(
                select(User, UserSettings)
                .join(UserSettings)
                .where(UserSettings.reminder_enabled.is_(True))
            )
            for user, settings in settings_rows:
                try:
                    local_now = now_utc.astimezone(
                        ZoneInfo(settings.timezone or self.default_timezone)
                    )
                except Exception:
                    local_now = now_utc.astimezone(ZoneInfo(self.default_timezone))
                if (
                    local_now.hour != settings.reminder_hour
                    or settings.last_reminder_date == local_now.date()
                ):
                    continue
                due_count = await session.scalar(
                    select(func.count(ReviewSchedule.id)).where(
                        ReviewSchedule.user_id == user.id, ReviewSchedule.next_review <= now_utc
                    )
                )
                settings.last_reminder_date = local_now.date()
                if due_count:
                    await bot.send_message(
                        user.telegram_id,
                        f"🔄 Время повторения.\n\nСегодня нужно повторить {due_count} элементов.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Начать повторение", callback_data="review:start"
                                    )
                                ]
                            ]
                        ),
                    )
            await session.commit()
