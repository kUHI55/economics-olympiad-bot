import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import build_router
from app.bot.middlewares import DatabaseSessionMiddleware
from app.core.config import get_settings
from app.database.session import create_session_factory
from app.services.llm import OpenAiLlmClient, UnavailableLlmClient
from app.services.notifications import ReminderService


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    session_factory = create_session_factory(settings.database_url)
    if settings.llm_api_key:
        llm = OpenAiLlmClient(settings.llm_api_key.get_secret_value(), settings.llm_model)
    else:
        llm = UnavailableLlmClient()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(settings=settings, llm=llm)
    dispatcher.update.middleware(DatabaseSessionMiddleware(session_factory))
    dispatcher.include_router(build_router())

    stop_event = asyncio.Event()
    reminder_task = asyncio.create_task(
        ReminderService(session_factory, settings.timezone).run(bot, stop_event),
        name="daily-reminders",
    )
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
    finally:
        stop_event.set()
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
