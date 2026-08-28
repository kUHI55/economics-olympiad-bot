from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.main import ensure_telegram_user
from app.bot.keyboards.common import list_keyboard
from app.bot.keyboards.quiz import answer_options_keyboard, retry_keyboard
from app.bot.states.quiz import ActiveQuiz
from app.core.config import Settings
from app.core.enums import AttemptVerdict, QuestionType, QuizMode
from app.database.repositories.catalog import CatalogRepository
from app.services.llm.client import LlmClient, LlmUnavailable
from app.services.progress.service import ProgressService
from app.services.quiz.evaluator import AnswerEvaluationService
from app.services.quiz.service import QuizService

router = Router(name="quiz")


async def start_quiz(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user_id: int,
    mode: QuizMode,
    scope_type: str = "all",
    scope_id: int | None = None,
    question_types: set[QuestionType] | None = None,
    only_knowledge_element_ids: list[int] | None = None,
    only_question_ids: list[int] | None = None,
) -> None:
    quiz = await QuizService(session).create_session(
        user_id=user_id,
        mode=mode,
        scope_type=scope_type,
        scope_id=scope_id,
        question_types=question_types,
        only_knowledge_element_ids=only_knowledge_element_ids,
        only_question_ids=only_question_ids,
    )
    if not quiz.total_questions:
        await message.answer(
            "В этом разделе пока нет подходящих вопросов. Добавь и подтверди материал."
        )
        return
    await state.set_state(ActiveQuiz.waiting_answer)
    await state.set_data(
        quiz_session_id=quiz.id,
        position=1,
        total=quiz.total_questions,
        user_id=user_id,
        hint_used=False,
        mode=mode.value,
    )
    await show_current_question(message, state, session)


async def show_current_question(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    quiz_service = QuizService(session)
    question = await quiz_service.question_at(data["quiz_session_id"], data["position"])
    if question is None:
        await finish_quiz(message, state, session)
        return
    await state.update_data(question_id=question.id, hint_used=False)
    text = f"Вопрос {data['position']}/{data['total']}\n\n{question.question}"
    if question.question_type is QuestionType.MULTIPLE_CHOICE:
        await message.answer(text, reply_markup=answer_options_keyboard(question))
    else:
        await message.answer(text + "\n\nНапиши ответ одним сообщением.")


async def finish_quiz(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    correct, total, type_totals = await QuizService(session).finish(data["quiz_session_id"])
    await state.clear()
    by_type = "\n".join(
        f"• {question_type.value}: {count}" for question_type, count in type_totals.items()
    )
    await message.answer(
        f"✅ Результат: {correct}/{total}\n\nСостав проверки:\n{by_type or 'нет вопросов'}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Посмотреть ошибки",
                        callback_data=f"quiz:errors:{data['quiz_session_id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Повторить ошибки",
                        callback_data=f"quiz:repeat-errors:{data['quiz_session_id']}",
                    )
                ],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
            ]
        ),
    )


async def _next_question(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.update_data(position=data["position"] + 1)
    await show_current_question(message, state, session)


async def _evaluate_answer(
    *, message: Message, state: FSMContext, session: AsyncSession, llm: LlmClient, raw_answer: str
) -> None:
    data = await state.get_data()
    quiz_service = QuizService(session)
    question = await quiz_service.question_at(data["quiz_session_id"], data["position"])
    if question is None:
        await finish_quiz(message, state, session)
        return
    try:
        evaluation = await AnswerEvaluationService(llm).evaluate(question, raw_answer)
    except LlmUnavailable:
        await message.answer(
            "Проверка свободного ответа недоступна: настрой LLM_API_KEY. "
            "Формулы и тесты можно проверять без него."
        )
        return
    await ProgressService(session).record_attempt(
        user_id=data["user_id"],
        question=question,
        answer=raw_answer,
        verdict=evaluation.verdict,
        score=evaluation.score,
        feedback=evaluation.model_dump(mode="json"),
        hint_used=data.get("hint_used", False),
        answer_revealed=False,
        quiz_session_id=data["quiz_session_id"],
    )
    # Mode is kept in the state to avoid another query in the answer hot path.
    is_exam = data.get("mode") == QuizMode.EXAM.value
    if is_exam or evaluation.verdict is AttemptVerdict.CORRECT:
        await quiz_service.mark_completed(data["quiz_session_id"], data["position"])
        if is_exam:
            await message.answer("Ответ сохранён. Следующий вопрос.")
        else:
            await message.answer("✅ Верно.")
        await _next_question(message, state, session)
        return
    if evaluation.verdict is AttemptVerdict.UNCERTAIN:
        reply = (
            "⚠️ Не удалось надёжно оценить ответ по сохранённому фрагменту. Попробуй уточнить мысль."
        )
    elif evaluation.verdict is AttemptVerdict.PARTIAL:
        missing = "; ".join(evaluation.missing_points[:2])
        reply = "◐ Ответ неполный. Попробуй ещё раз." + (
            f" Не хватает: {missing}." if missing else ""
        )
    else:
        reply = "❌ Неправильно. Попробуй ещё раз."
    await message.answer(reply, reply_markup=retry_keyboard())


@router.message(F.text == "🧠 Проверка")
async def quiz_menu(message: Message) -> None:
    await message.answer(
        "Выбери область проверки.",
        reply_markup=list_keyboard(
            [
                ("По теме", "quiz:select:topic"),
                ("По разделу", "quiz:select:section"),
                ("Вся экономика", "quiz:scope:all:0"),
                ("⚡ Блиц", "quiz:mode:blitz"),
                ("🎓 Экзамен", "quiz:mode:exam"),
            ]
        ),
    )


@router.callback_query(F.data == "quiz:menu")
async def quiz_menu_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await quiz_menu(callback.message)


@router.callback_query(F.data == "quiz:select:section")
async def select_quiz_section(callback: CallbackQuery, session: AsyncSession) -> None:
    sections = await CatalogRepository(session).list_sections()
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери раздел.",
            reply_markup=list_keyboard(
                [(section.name, f"quiz:scope:section:{section.id}") for section in sections],
                back="quiz:menu",
            ),
        )


@router.callback_query(F.data == "quiz:select:topic")
async def select_quiz_topic_section(callback: CallbackQuery, session: AsyncSession) -> None:
    sections = await CatalogRepository(session).list_sections()
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Сначала выбери раздел.",
            reply_markup=list_keyboard(
                [(section.name, f"quiz:topicsection:{section.id}") for section in sections],
                back="quiz:menu",
            ),
        )


@router.callback_query(F.data.startswith("quiz:topicsection:"))
async def select_quiz_topic(callback: CallbackQuery, session: AsyncSession) -> None:
    section_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    topics = await CatalogRepository(session).list_topics(section_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери тему.",
            reply_markup=list_keyboard(
                [(topic.name, f"quiz:scope:topic:{topic.id}") for topic in topics],
                back="quiz:select:topic",
            ),
        )


@router.callback_query(F.data.startswith("quiz:scope:"))
async def select_quiz_type(callback: CallbackQuery) -> None:
    _, _, scope_type, raw_scope_id = callback.data.split(":")
    scope_id = int(raw_scope_id)
    await callback.answer()
    if callback.message:
        prefix = f"quiz:begin:practice:{scope_type}:{scope_id}"
        await callback.message.answer(
            "Выбери формат вопросов.",
            reply_markup=list_keyboard(
                [
                    ("Формулы", f"{prefix}:formula"),
                    ("Определения", f"{prefix}:definition"),
                    ("Понимание", f"{prefix}:understanding"),
                    ("Тест", f"{prefix}:multiple_choice"),
                    ("Смешанный", f"{prefix}:mixed"),
                ],
                back="quiz:menu",
            ),
        )


@router.callback_query(F.data.startswith("quiz:begin:"))
async def begin_practice(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    _, _, raw_mode, scope_type, raw_scope_id, raw_type = callback.data.split(":")
    if not callback.message:
        return
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user:
        return
    mode = QuizMode(raw_mode)
    question_types = None if raw_type == "mixed" else {QuestionType(raw_type)}
    await callback.answer()
    await start_quiz(
        message=callback.message,
        state=state,
        session=session,
        user_id=user.id,
        mode=mode,
        scope_type=scope_type,
        scope_id=None if raw_scope_id == "0" else int(raw_scope_id),
        question_types=question_types,
    )


@router.callback_query(F.data.startswith("quiz:mode:"))
async def begin_special_mode(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not callback.message:
        return
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user:
        return
    raw_mode = callback.data.rsplit(":", maxsplit=1)[1]
    mode = QuizMode.BLITZ if raw_mode == "blitz" else QuizMode.EXAM
    await callback.answer()
    await start_quiz(
        message=callback.message,
        state=state,
        session=session,
        user_id=user.id,
        mode=mode,
    )


@router.message(ActiveQuiz.waiting_answer, F.text)
async def free_answer(
    message: Message, state: FSMContext, session: AsyncSession, llm: LlmClient
) -> None:
    await _evaluate_answer(
        message=message, state=state, session=session, llm=llm, raw_answer=message.text
    )


@router.callback_query(ActiveQuiz.waiting_answer, F.data.startswith("quiz:answer:"))
async def choice_answer(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, llm: LlmClient
) -> None:
    data = await state.get_data()
    question = await QuizService(session).question_at(data["quiz_session_id"], data["position"])
    option_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    if not question or not any(option.id == option_id for option in question.options):
        await callback.answer("Этот вариант уже неактуален.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await _evaluate_answer(
            message=callback.message,
            state=state,
            session=session,
            llm=llm,
            raw_answer=str(option_id),
        )


@router.callback_query(ActiveQuiz.waiting_answer, F.data == "quiz:retry")
async def retry_question(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message:
        await show_current_question(callback.message, state, session)


@router.callback_query(ActiveQuiz.waiting_answer, F.data == "quiz:hint")
async def show_hint(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    question = await QuizService(session).question_at(data["quiz_session_id"], data["position"])
    await state.update_data(hint_used=True)
    await callback.answer()
    if callback.message and question:
        await callback.message.answer(
            f"💡 Подсказка: {question.hint}", reply_markup=retry_keyboard()
        )


@router.callback_query(ActiveQuiz.waiting_answer, F.data == "quiz:reveal")
async def reveal_answer(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    quiz_service = QuizService(session)
    question = await quiz_service.question_at(data["quiz_session_id"], data["position"])
    if not question:
        return
    await ProgressService(session).mark_answer_revealed(
        user_id=data["user_id"], question_id=question.id, quiz_session_id=data["quiz_session_id"]
    )
    await quiz_service.mark_completed(data["quiz_session_id"], data["position"])
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Ответ: {question.reference_answer}\n\nОбъяснение: {question.explanation}"
        )
        await _next_question(callback.message, state, session)


@router.callback_query(F.data.startswith("quiz:errors:"))
async def show_session_errors(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    session_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user or not await QuizService(session).belongs_to_user(session_id, user.id):
        await callback.answer("Эта сессия недоступна.", show_alert=True)
        return
    questions = await QuizService(session).error_question_texts(session_id)
    await callback.answer()
    if callback.message:
        text = "\n".join(f"• {question}" for question in questions)
        await callback.message.answer(f"Ошибки:\n{text or 'Ошибок нет.'}")


@router.callback_query(F.data.startswith("quiz:repeat-errors:"))
async def repeat_session_errors(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not callback.message:
        return
    previous_session_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    user = await ensure_telegram_user(callback.from_user, session, settings)
    if not user:
        return
    quiz_service = QuizService(session)
    if not await quiz_service.belongs_to_user(previous_session_id, user.id):
        await callback.answer("Эта сессия недоступна.", show_alert=True)
        return
    question_ids = await quiz_service.error_question_ids(previous_session_id)
    await callback.answer()
    if not question_ids:
        await callback.message.answer("В этой сессии нет ошибок для повторения.")
        return
    await start_quiz(
        message=callback.message,
        state=state,
        session=session,
        user_id=user.id,
        mode=QuizMode.PRACTICE,
        only_question_ids=question_ids,
    )
