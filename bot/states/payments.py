from aiogram.fsm.state import State, StatesGroup


class PaymentForm(StatesGroup):
    tutor = State()
    amount = State()
    allocations = State()
    notes = State()
    confirmation = State()
    history_tutor = State()
