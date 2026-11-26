from aiogram.fsm.state import State, StatesGroup


class PaymentForm(StatesGroup):
    assignment = State()
    amount = State()
    notes = State()
    confirmation = State()
