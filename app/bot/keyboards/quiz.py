from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models.content import Question


def answer_options_keyboard(question: Question) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=option.option_text, callback_data=f"quiz:answer:{option.id}"
                )
            ]
            for option in question.options
        ]
    )


def retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Попробовать ещё раз", callback_data="quiz:retry")],
            [InlineKeyboardButton(text="Подсказка", callback_data="quiz:hint")],
            [InlineKeyboardButton(text="Показать ответ", callback_data="quiz:reveal")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )
