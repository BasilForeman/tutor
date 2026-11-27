
from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    client = State()
    new_client_nickname = State()
    new_client_contact = State()
    source = State()
    subject = State()
    notes = State()
    search = State()
    edit_id = State()
    edit_subject = State()
    edit_notes = State()
    status_id = State()
    status = State()
    lost_reason = State()
    filter_status = State()
