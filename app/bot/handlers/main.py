from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import home_keyboard
from app.core.config import Settings
from app.database.repositories.user import UserRepository

router = Router(name="main")


async def ensure_telegram_user(
    telegram_user: TelegramUser | None, session: AsyncSession, settings: Settings
):
    if telegram_user is None:
        return None
    return await UserRepository(session).get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        display_name=telegram_user.full_name,
        is_admin=telegram_user.id == settings.admin_id,
    )


async def ensure_user(message: Message, session: AsyncSession, settings: Settings):
    return await ensure_telegram_user(message.from_user, session, settings)


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession, settings: Settings) -> None:
    await ensure_user(message, session, settings)
    await message.answer(
        "Привет! Это твоя база изученной теории и тренажёр воспроизведения.\n\n"
        "Я буду опираться только на сохранённые тобой источники, а не дополнять их теорией от себя.",
        reply_markup=home_keyboard(),
    )


@router.callback_query(F.data == "menu:home")
async def go_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer("Главное меню", reply_markup=home_keyboard())


@router.message(F.text == "⚙️ Настройки")
async def settings_view(message: Message, session: AsyncSession, settings: Settings) -> None:
    user = await ensure_user(message, session, settings)
    if not user:
        return
    settings_data = user.settings
    status = "включены" if settings_data and settings_data.reminder_enabled else "выключены"
    hour = settings_data.reminder_hour if settings_data else settings.reminder_hour
    await message.answer(
        f"⚙️ Напоминания: {status}\nВремя: {hour:02d}:00\nЧасовой пояс: "
        f"{settings_data.timezone if settings_data else settings.timezone}\n\n"
        "В MVP время задаётся в .env; здесь видны текущие настройки."
    )
