# Tutor CRM bot

Python async Telegram bot (aiogram 3), PostgreSQL via SQLAlchemy 2, and Google Sheets export.

## Local setup

1. Use Python 3.11 or newer. The bundled `venv` was created with Python 3.9, which is end-of-life; create a fresh environment before deployment.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN`, `ADMIN_ID`, and a local/test `DATABASE_URL`. Google Sheets settings are only needed when testing the export. Never commit `.env` or service-account JSON.
4. Start the local database with `docker compose up -d db`.
5. For a new empty database, run `python create_tables.py`, then review and apply SQL migrations `0001`–`0005` to the confirmed local database. For an existing database, do not run `create_tables.py`; review `migrations/README.md` and apply the migrations to a test copy first. The repository has no automated migration ledger yet.
6. Start the bot with `python -m bot.main`.

## Checks

- Unit tests: `python -m unittest discover -s tests -v`
- Import smoke check: set a dummy `DATABASE_URL` and import the modules; it does not verify database connectivity.
- Database/schema and Google Sheets scripts connect to configured services. Run them only after checking that `.env` points to local/test resources.
