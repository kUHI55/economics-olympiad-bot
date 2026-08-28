from aiogram.fsm.state import State, StatesGroup


class AddMaterial(StatesGroup):
    choosing_section = State()
    waiting_new_section = State()
    choosing_topic = State()
    waiting_new_topic = State()
    choosing_subtopic = State()
    waiting_new_subtopic = State()
    waiting_content = State()
