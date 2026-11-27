from aiogram.fsm.state import State, StatesGroup


class CommissionAdjustmentForm(StatesGroup):
    assignment = State()
    amount = State()
    reason = State()
    confirmation = State()


class RefundForm(StatesGroup):
    assignment = State()
    payment = State()
    amount = State()
    reason = State()
    confirmation = State()
