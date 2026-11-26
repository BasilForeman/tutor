from aiogram.fsm.state import State, StatesGroup


class AssignmentForm(StatesGroup):
    lead = State()
    tutor = State()
    assigned_by = State()
    rate = State()
    commission_multiplier = State()
    payment_due_date = State()
    confirmation = State()
    close_assignment = State()
    close_reason = State()
    close_confirmation = State()
