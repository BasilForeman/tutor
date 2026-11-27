# Tutor CRM bot

Python async Telegram bot (aiogram 3), PostgreSQL via SQLAlchemy 2, and Google Sheets export.

## Local setup

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for Sonya's Telegram workflow, including manual creation of a tutor, student, lead, and assignment.

1. Use Python 3.12. The original `venv` is still tied to Python 3.9.6 and should not be used. The verified `venv_new` uses Python 3.12.16.
2. Install dependencies in that environment with `./venv_new/bin/python -m pip install -r requirements.txt`. Check them with `./venv_new/bin/python -m pip check`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN`, `ADMIN_ID`, and a local/test `DATABASE_URL`. Google Sheets settings are only needed when testing the export. Never commit `.env` or service-account JSON.
   `ADMIN_ID` accepts comma-separated Telegram IDs. FSM state persists in PostgreSQL by default (`FSM_STORAGE=postgres`); overdue reminders default to 10:00 Europe/Moscow and can be disabled with `DEBT_REMINDERS_ENABLED=false`. Google Sheets automatic full snapshots are opt-in (`GOOGLE_SHEETS_SYNC_ENABLED=true`); admins can also start a manual sync in the bot.
4. Start the local database with `docker compose up -d db`.
5. For a new empty database, run `python create_tables.py`, then review and apply SQL migrations `0001`–`0012` to the confirmed local database. For an existing database, do not run `create_tables.py`; review `migrations/README.md` and apply the migrations to a test copy first. The repository has no automated migration ledger yet.
6. Start the bot with `./venv_new/bin/python -m bot.main`.

## Checks

- Unit tests: `./venv_new/bin/python -m unittest discover -s tests -v`
- Import smoke check: set a dummy `DATABASE_URL` and import the modules; it does not verify database connectivity.
- Database/schema and Google Sheets scripts connect to configured services. Run them only after checking that `.env` points to local/test resources.
- On 2026-11-27 migrations 0001–0012 and the Lead → Assignment → four lessons → commission → payment → analytics service path passed on a disposable PostgreSQL 17 tmpfs cluster. The test Google spreadsheet and Telegram bot were used only in the previously authorized synthetic smoke test, as recorded in `docs/AUDIT_REPORT.md`.

### Disposable PostgreSQL migration checks

The isolated test service has its own port (55433), credentials, and a tmpfs data directory; it does not use `postgres_data` or the `tutor_bot_db` container from `docker-compose.yml`:

```sh
docker compose -f docker-compose.test.yml up -d --wait db-test
```

Apply reviewed migrations 0001–0012 only to `tutor_bot_test` at `127.0.0.1:55433`. The test cluster has no persistent data. Remove only the test service after checking with:

```sh
docker compose -f docker-compose.test.yml rm -sf db-test
```

### Google Sheets setup

The integration uses a Google Cloud service account JSON file via `google-auth` and `gspread`, with the Google Sheets scope. Enable the Google Sheets API for that Cloud project, set `GOOGLE_CREDENTIALS_PATH` and `GOOGLE_SHEETS_ID` in local `.env`, and share the target spreadsheet with the service account email as an Editor. Keep the JSON key out of Git. For a first write test, use a separate test spreadsheet or an agreed copy. Manual sync is the admin-only `📊 Синхронизировать Sheets` action; automatic snapshots are opt-in with `GOOGLE_SHEETS_SYNC_ENABLED=true` and the configured interval. Do not run either against a real spreadsheet until the target is confirmed.
