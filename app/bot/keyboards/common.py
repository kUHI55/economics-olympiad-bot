from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def home_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Теория"), KeyboardButton(text="🧠 Проверка")],
            [KeyboardButton(text="🔄 Повторение"), KeyboardButton(text="📊 Прогресс")],
            [KeyboardButton(text="⚠️ Слабые места"), KeyboardButton(text="➕ Добавить материал")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def navigation_keyboard(back_callback: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def list_keyboard(
    items: Sequence[tuple[str, str]],
    *,
    extra: Sequence[tuple[str, str]] = (),
    back: str = "menu:home",
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=text, callback_data=callback)] for text, callback in items]
    rows.extend(
        [InlineKeyboardButton(text=text, callback_data=callback)] for text, callback in extra
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
