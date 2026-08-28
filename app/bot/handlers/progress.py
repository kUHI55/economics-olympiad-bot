from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.main import ensure_telegram_user, ensure_user
from app.bot.keyboards.common import list_keyboard
from app.core.config import Settings
from app.core.enums import QuizMode
from app.database.repositories.catalog import CatalogRepository
from app.database.repositories.learning import LearningRepository
from app.services.progress.stats import StatisticsService
from app.services.progress.weak_areas import WeakAreasService

router = Router(name="progress")


@router.message(F.text == "📚 Теория")
async def theory_menu(message: Message, session: AsyncSession) -> None:
    sections = await CatalogRepository(session).list_sections()
    if not sections:
        await message.answer(
            "База теории пока пуста. Добавь первый материал через «➕ Добавить материал»."
        )
        return
    await message.answer(
        "Выбери раздел.",
        reply_markup=list_keyboard(
            [(section.name, f"theory:section:{section.id}") for section in sections]
        ),
    )


@router.callback_query(F.data.startswith("theory:section:"))
async def theory_topics(callback: CallbackQuery, session: AsyncSession) -> None:
    section_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    topics = await CatalogRepository(session).list_topics(section_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Темы раздела.",
            reply_markup=list_keyboard(
                [(topic.name, f"theory:topic:{topic.id}") for topic in topics], back="theory:menu"
            ),
        )


@router.callback_query(F.data.startswith("theory:topic:"))
async def theory_subtopics(callback: CallbackQuery, session: AsyncSession) -> None:
    topic_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    subtopics = await CatalogRepository(session).list_subtopics(topic_id)
    await callback.answer()
    if callback.message:
        names = (
            "\n".join(f"• {subtopic.name}" for subtopic in subtopics) or "• Без выделенных подтем"
        )
        await callback.message.answer(
            f"Подтемы:\n{names}\n\nДля проверки этой темы используй «🧠 Проверка»."
        )


@router.callback_query(F.data == "theory:menu")
async def theory_menu_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message:
        await theory_menu(callback.message, session)


@router.message(F.text == "📊 Прогресс")
async def progress_view(message: Message, session: AsyncSession, settings: Settings) -> None:
    user = await ensure_user(message, session, settings)
    if not user:
        return
    summary = await StatisticsService(session).summary(user.id)
    topics = "\n".join(f"• {item.topic_name} — {item.score:.0%}" for item in summary.topics)
    types = "\n".join(
        f"• {item.question_type.value}: {item.correct}/{item.total} ({item.score:.0%})"
        for item in summary.question_types
    )
    await message.answer(
        "📊 Прогресс\n\n"
        f"Всего элементов: {summary.total_elements}\n"
        f"Проверено: {summary.reviewed_elements}\n"
        f"Ответов: {summary.attempts}\n"
        f"Правильных: {summary.correct}\n"
        f"Ошибок: {summary.incorrect}\n\n"
        f"По темам:\n{topics or 'Пока нет попыток.'}\n\n"
        f"По типам вопросов:\n{types or 'Пока нет попыток.'}"
    )


@router.message(F.text == "🔄 Повторение")
async def review_menu(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    user = await ensure_user(message, session, settings)
    if not user:
        return
    element_ids = await LearningRepository(session).due_review_element_ids(user.id)
    if not element_ids:
        await message.answer("🔄 На сегодня повторений нет.")
        return
    await message.answer(
        f"🔄 Сегодня нужно повторить {len(element_ids)} элементов.",
        reply_markup=list_keyboard([("Начать", "review:start")]),
    )


@router.callback_query(F.data == "review:start")
async def start_review(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not callback.message:
        return
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user:
        return
    element_ids = await LearningRepository(session).due_review_element_ids(user.id)
    await callback.answer()
    if not element_ids:
        await callback.message.answer("Повторений на сегодня уже нет.")
        return
    from app.bot.handlers.quiz import start_quiz

    await start_quiz(
        message=callback.message,
        state=state,
        session=session,
        user_id=user.id,
        mode=QuizMode.REVIEW,
        only_knowledge_element_ids=element_ids,
    )


@router.message(F.text == "⚠️ Слабые места")
async def weak_areas_view(message: Message, session: AsyncSession, settings: Settings) -> None:
    user = await ensure_user(message, session, settings)
    if not user:
        return
    summary = await StatisticsService(session).summary(user.id)
    weak = [item for item in summary.topics if item.score < 0.8]
    lines = "\n".join(f"• {item.topic_name} — {item.score:.0%}" for item in weak)
    if not lines:
        lines = "Пока недостаточно попыток или слабых тем не найдено."
    await message.answer(
        f"⚠️ Слабые места\n\n{lines}",
        reply_markup=list_keyboard([("Проверить слабые места", "weak:start")]),
    )


@router.callback_query(F.data == "weak:start")
async def start_weak_areas(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not callback.message:
        return
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user:
        return
    element_ids = await WeakAreasService(session).element_ids(user.id)
    await callback.answer()
    if not element_ids:
        await callback.message.answer("Пока нет данных для подбора слабых мест.")
        return
    from app.bot.handlers.quiz import start_quiz

    await start_quiz(
        message=callback.message,
        state=state,
        session=session,
        user_id=user.id,
        mode=QuizMode.WEAK_AREAS,
        only_knowledge_element_ids=element_ids,
    )
