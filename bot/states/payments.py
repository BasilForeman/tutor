from aiogram.fsm.state import State, StatesGroup


class PaymentForm(StatesGroup):
    tutor = State()
    amount = State()
    overpayment_confirmation = State()
    allocation_select = State()
    allocation_amount = State()
    advance_remainder_confirmation = State()
    notes = State()
    confirmation = State()
    history_tutor = State()
    advance_tutor = State()
    advance_batch = State()
    advance_select = State()
    advance_amount = State()
    advance_confirmation = State()
