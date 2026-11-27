# Tutor CRM bot

Python async Telegram bot (aiogram 3), PostgreSQL via SQLAlchemy 2, and Google Sheets export.

## Local setup

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for exact local startup instructions, safe disposable-database setup, implemented buttons, and manual assignment test scenarios.

1. Use Python 3.12. The original `venv` is still tied to Python 3.9.6 and should not be used. The verified `venv_new` uses Python 3.12.16.
2. Install dependencies in that environment with `./venv_new/bin/python -m pip install -r requirements.txt`. Check them with `./venv_new/bin/python -m pip check`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN`, `ADMIN_ID`, and a local/test `DATABASE_URL`. Google Sheets settings are only needed when testing the export. Never commit `.env` or service-account JSON.
   `ADMIN_ID` accepts comma-separated Telegram IDs. FSM state persists in PostgreSQL by default (`FSM_STORAGE=postgres`); overdue reminders default to 10:00 Europe/Moscow and can be disabled with `DEBT_REMINDERS_ENABLED=false`. Google Sheets automatic full snapshots are opt-in (`GOOGLE_SHEETS_SYNC_ENABLED=true`); admins can also start a manual sync in the bot.
4. For a safe manual Telegram test, use only `docker-compose.test.yml` and follow the commands in [docs/USER_GUIDE.md](docs/USER_GUIDE.md). That guide explicitly overrides `DATABASE_URL` for both schema initialization and bot startup and disables scheduled notifications/sync.
5. `create_tables.py` only creates the current model schema on an empty database; it does not upgrade an existing schema and does not create the `assignment_finances` view. Numbered SQL migrations are manual and there is no migration ledger. Do not run `create_tables.py` or migrations against an existing database without a reviewed copy and rollout plan. See [migrations/README.md](migrations/README.md).
6. The bot entry point is `./venv_new/bin/python -m bot.main`; before running it, make sure the environment points to the intended test database and a test bot token.

## Checks

- Unit tests: `./venv_new/bin/python -m unittest discover -s tests -v`
- Import smoke check: set a dummy `DATABASE_URL` and import the modules; it does not verify database connectivity.
- Database/schema and Google Sheets scripts connect to configured services. Run them only after checking that `.env` points to local/test resources.
- Migration status is not recorded in a version table. The current local schema was inspected read-only and has the structural signatures through 0012, but the exact migration execution history cannot be proven. Do not rerun migrations against it; see [AUDIT_REPORT.md](docs/AUDIT_REPORT.md).
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
