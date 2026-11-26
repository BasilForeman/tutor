
from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    client = State()
    new_client_nickname = State()
    new_client_contact = State()
    source = State()
    subject = State()
    notes = State()
