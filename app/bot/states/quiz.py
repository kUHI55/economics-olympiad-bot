from aiogram.fsm.state import State, StatesGroup


class ActiveQuiz(StatesGroup):
    waiting_answer = State()
