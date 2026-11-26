from aiogram.fsm.state import State, StatesGroup


class LessonForm(StatesGroup):
    assignment = State()
    lesson_type = State()
    status = State()
    lesson_date = State()
    amount = State()
    notes = State()
    confirmation = State()
