from datetime import datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.main import ensure_user
from app.bot.keyboards.common import home_keyboard, list_keyboard
from app.bot.states.material import AddMaterial
from app.core.config import Settings
from app.core.enums import SourceType
from app.database.models.content import MaterialDraft
from app.database.repositories.catalog import CatalogRepository
from app.database.repositories.user import UserRepository
from app.schemas.analysis import MaterialAnalysis
from app.services.llm.client import LlmClient, LlmUnavailable
from app.services.theory.analyzer import SourceAnalyzerService
from app.services.theory.extractor import UnsupportedSourceError, extract_file_text
from app.services.theory.publisher import SourcePublisher

router = Router(name="material")


def _is_admin(message: Message | CallbackQuery, settings: Settings) -> bool:
    user = message.from_user
    return bool(user and user.id == settings.admin_id)


async def _show_sections(message: Message, session: AsyncSession) -> None:
    sections = await CatalogRepository(session).list_sections()
    await message.answer(
        "Выбери раздел для материала.",
        reply_markup=list_keyboard(
            [(section.name, f"material:section:{section.id}") for section in sections],
            extra=[("➕ Создать раздел", "material:section:new")],
        ),
    )


async def _show_topics(message: Message, session: AsyncSession, section_id: int) -> None:
    topics = await CatalogRepository(session).list_topics(section_id)
    await message.answer(
        "Выбери тему.",
        reply_markup=list_keyboard(
            [(topic.name, f"material:topic:{topic.id}") for topic in topics],
            extra=[("➕ Создать тему", "material:topic:new")],
            back="material:back:sections",
        ),
    )


async def _show_subtopics(message: Message, session: AsyncSession, topic_id: int) -> None:
    subtopics = await CatalogRepository(session).list_subtopics(topic_id)
    await message.answer(
        "Выбери подтему или сохрани материал прямо в теме.",
        reply_markup=list_keyboard(
            [(subtopic.name, f"material:subtopic:{subtopic.id}") for subtopic in subtopics],
            extra=[
                ("Без подтемы", "material:subtopic:0"),
                ("➕ Создать подтему", "material:subtopic:new"),
            ],
            back="material:back:topics",
        ),
    )


@router.message(F.text == "➕ Добавить материал")
async def begin_material(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Добавлять и изменять материалы может только администратор.")
        return
    await state.clear()
    await state.set_state(AddMaterial.choosing_section)
    await _show_sections(message, session)


@router.callback_query(AddMaterial.choosing_section, F.data == "material:section:new")
async def ask_section_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddMaterial.waiting_new_section)
    if callback.message:
        await callback.message.answer("Напиши название нового раздела.")


@router.message(AddMaterial.waiting_new_section, F.text)
async def create_section(message: Message, state: FSMContext, session: AsyncSession) -> None:
    section = await CatalogRepository(session).create_section(message.text)
    await state.update_data(section_id=section.id)
    await state.set_state(AddMaterial.choosing_topic)
    await _show_topics(message, session, section.id)


@router.callback_query(AddMaterial.choosing_section, F.data.startswith("material:section:"))
async def select_section(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    section_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    await state.update_data(section_id=section_id)
    await state.set_state(AddMaterial.choosing_topic)
    await callback.answer()
    if callback.message:
        await _show_topics(callback.message, session, section_id)


@router.callback_query(AddMaterial.choosing_topic, F.data == "material:topic:new")
async def ask_topic_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddMaterial.waiting_new_topic)
    if callback.message:
        await callback.message.answer("Напиши название новой темы.")


@router.message(AddMaterial.waiting_new_topic, F.text)
async def create_topic(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    topic = await CatalogRepository(session).create_topic(data["section_id"], message.text)
    await state.update_data(topic_id=topic.id)
    await state.set_state(AddMaterial.choosing_subtopic)
    await _show_subtopics(message, session, topic.id)


@router.callback_query(AddMaterial.choosing_topic, F.data.startswith("material:topic:"))
async def select_topic(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    topic_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    await state.update_data(topic_id=topic_id)
    await state.set_state(AddMaterial.choosing_subtopic)
    await callback.answer()
    if callback.message:
        await _show_subtopics(callback.message, session, topic_id)


@router.callback_query(AddMaterial.choosing_subtopic, F.data == "material:subtopic:new")
async def ask_subtopic_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddMaterial.waiting_new_subtopic)
    if callback.message:
        await callback.message.answer("Напиши название новой подтемы.")


@router.message(AddMaterial.waiting_new_subtopic, F.text)
async def create_subtopic(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    subtopic = await CatalogRepository(session).create_subtopic(data["topic_id"], message.text)
    await _prepare_content(message, state, subtopic.id)


@router.callback_query(AddMaterial.choosing_subtopic, F.data.startswith("material:subtopic:"))
async def select_subtopic(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.rsplit(":", maxsplit=1)[1]
    await callback.answer()
    if callback.message:
        await _prepare_content(callback.message, state, None if value == "0" else int(value))


async def _prepare_content(message: Message, state: FSMContext, subtopic_id: int | None) -> None:
    await state.update_data(subtopic_id=subtopic_id)
    await state.set_state(AddMaterial.waiting_content)
    await message.answer(
        "Отправь текст или файл TXT, PDF, DOCX либо Markdown. После анализа ничего не сохранится без подтверждения."
    )


async def _create_proposal(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    llm: LlmClient,
    settings: Settings,
    source_name: str,
    source_type: SourceType,
    content: str,
    file_path: str | None,
) -> None:
    try:
        analysis = await SourceAnalyzerService(llm).analyze(
            source_name=source_name, source_type=source_type, content=content
        )
    except LlmUnavailable:
        if file_path:
            Path(file_path).unlink(missing_ok=True)
        await message.answer(
            "Анализ недоступен: в .env не задан LLM_API_KEY. Материал не сохранён."
        )
        return
    except Exception:
        if file_path:
            Path(file_path).unlink(missing_ok=True)
        await message.answer(
            "Не удалось надёжно проанализировать материал. Ничего не сохранено — попробуй ещё раз."
        )
        return
    data = await state.get_data()
    user = await ensure_user(message, session, settings=settings)
    if user is None:
        return
    draft = MaterialDraft(
        created_by_id=user.id,
        section_id=data["section_id"],
        topic_id=data["topic_id"],
        subtopic_id=data.get("subtopic_id"),
        source_name=source_name,
        source_type=source_type,
        source_date=datetime.now().date(),
        content=content,
        file_path=file_path,
        proposal=analysis.model_dump(mode="json"),
    )
    session.add(draft)
    await session.flush()
    counts = analysis.counts()
    warnings = "\n".join(f"• {warning}" for warning in analysis.warnings[:3])
    await state.clear()
    await message.answer(
        "Из материала найдено:\n"
        f"• элементов знаний: {counts['elements']}\n"
        f"• определений: {counts['definitions']}\n"
        f"• формул: {counts['formulas']}\n"
        f"• механизмов: {counts['mechanisms']}\n"
        f"• вопросов: {counts['questions']}"
        + (f"\n\nПредупреждения:\n{warnings}" if warnings else ""),
        reply_markup=list_keyboard(
            [
                ("Сохранить", f"material:confirm:{draft.id}"),
                ("Отмена", f"material:cancel:{draft.id}"),
            ]
        ),
    )


@router.message(AddMaterial.waiting_content, F.text)
async def receive_text_material(
    message: Message, state: FSMContext, session: AsyncSession, llm: LlmClient, settings: Settings
) -> None:
    await _create_proposal(
        message=message,
        state=state,
        session=session,
        llm=llm,
        settings=settings,
        source_name=f"Текст из Telegram ({datetime.now():%Y-%m-%d %H:%M})",
        source_type=SourceType.TEXT,
        content=message.text,
        file_path=None,
    )


@router.message(AddMaterial.waiting_content, F.document)
async def receive_file_material(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    llm: LlmClient,
    settings: Settings,
    bot: Bot,
) -> None:
    document = message.document
    if document is None or not document.file_name:
        return
    suffix = Path(document.file_name).suffix.lower()
    path = settings.upload_dir / f"{document.file_unique_id}{suffix}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        await bot.download(document, destination=path)
        source_type, content = extract_file_text(path, document.file_name)
    except UnsupportedSourceError as exc:
        await message.answer(str(exc))
        return
    except Exception:
        await message.answer("Не удалось извлечь текст из файла. Ничего не сохранено.")
        return
    await _create_proposal(
        message=message,
        state=state,
        session=session,
        llm=llm,
        settings=settings,
        source_name=document.file_name,
        source_type=source_type,
        content=content,
        file_path=str(path),
    )


@router.callback_query(F.data.startswith("material:confirm:"))
async def confirm_material(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _is_admin(callback, settings):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    draft_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    draft = await session.get(MaterialDraft, draft_id)
    if draft is None:
        await callback.answer("Черновик уже недоступен.", show_alert=True)
        return
    if callback.from_user is None:
        return
    user = await UserRepository(session).get_or_create(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
        callback.from_user.id == settings.admin_id,
    )
    if draft.created_by_id != user.id:
        await callback.answer("Этот черновик принадлежит другому пользователю.", show_alert=True)
        return
    source = await SourcePublisher(session).publish(
        draft, MaterialAnalysis.model_validate(draft.proposal)
    )
    await callback.answer("Сохранено")
    if callback.message:
        await callback.message.answer(
            f"✅ Источник «{source.source_name}» и связанные с ним знания сохранены.",
            reply_markup=home_keyboard(),
        )


@router.callback_query(F.data.startswith("material:cancel:"))
async def cancel_material(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _is_admin(callback, settings):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    draft_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    draft = await session.get(MaterialDraft, draft_id)
    if draft:
        if callback.from_user is None:
            return
        user = await UserRepository(session).get_or_create(
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.full_name,
            callback.from_user.id == settings.admin_id,
        )
        if draft.created_by_id != user.id:
            await callback.answer(
                "Этот черновик принадлежит другому пользователю.", show_alert=True
            )
            return
        if draft.file_path:
            Path(draft.file_path).unlink(missing_ok=True)
        await session.delete(draft)
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.answer(
            "Черновик удалён. Материал не сохранён.", reply_markup=home_keyboard()
        )
