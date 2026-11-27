# Database migrations

## Current status and safe use

These numbered SQL files have no built-in version table or runner. The current local schema was inspected read-only on 2026-11-27: its relations, columns, indexes, constraints, and `assignment_finances` view have the postconditions expected through 0012, including `google_sheets_sync_log`. Since no migration ledger exists, this does not prove which scripts were run or in what order. Do not infer that a migration is pending from the absent ledger, and do not rerun scripts against the existing local database. No migrations were run during this inspection.

For an isolated manual test only, initialize a fresh `db-test` from `docker-compose.test.yml`, use `create_tables.py` with an explicit disposable `DATABASE_URL`, then apply files 0001–0012 once in numeric order. Exact commands are in `docs/USER_GUIDE.md`. `create_tables.py` creates the current ORM tables on an empty schema but does not create `assignment_finances`; the SQL chain supplies/replaces that view. It refuses to run when relations already exist.

Migrations 0005 and 0007 contain `DROP VIEW IF EXISTS assignment_finances` and recreate that derived view to change output-column types. They do not drop the backing data tables, but remain schema-changing SQL and must be exercised on a disposable database before any rollout.

Apply numbered SQL migrations in order, using a migration table/tracker in the deployment process. `0001_leads_and_assignment_link.sql` is transactional and additive. It preserves old assignments by creating one synthetic historical lead per legacy assignment before adding the required foreign key. If `assignment_finances` is an earlier table/materialized view, the migration renames it to `assignment_finances_legacy_0001` (retaining its rows) before creating the application-facing view from assignments and payments; compare that retained snapshot before a later manual cleanup.

Before applying, inspect the target database and take a restorable backup. Apply only to a confirmed local/test database first, inspect the resulting rows and constraints, then plan any production rollout separately. This repository does not yet include an Alembic runner or automated migration tracking; do not rerun a numbered migration blindly. The SQL is idempotent for schema additions, but the project still needs a migration ledger before repeatable deployment automation.


Migration `0002_payment_idempotency.sql` adds a nullable operation key to historical payments and a partial unique index. Existing payment records remain unchanged. Apply it after migration 0001 on a verified test database.


Migration `0003_lessons.sql` adds the lesson ledger (trial/paid, completed/cancelled), its Assignment foreign key, amount constraint and idempotency key. Existing tables are left intact.

Migration `0004_assignment_idempotency.sql` adds a nullable unique operation key. A new key allows an intentional repeated assignment; replays of the same FSM operation return the original record. Historical assignments retain a NULL key.

Migration `0005_short_term_commission.sql` stores the agreed rate multiplier and closure fields, creates append-only adjustment history, and replaces `assignment_finances` with a view that accrues long-term commission after the configured paid-lesson threshold (default 4). Closing after no more than the configured limit settles at 25% of actual completed paid lesson earnings; the original agreed amount remains intact and the difference is recorded as an adjustment. PostgreSQL will not change an existing view column's numeric type via `CREATE OR REPLACE VIEW`, so this revision drops/recreates only the derived view created by 0001. It does not use `CASCADE`; unexpected dependencies stop the migration safely.

Migration `0006_p0_2_lead_crud_and_history.sql` adds the tutor active flag, active case-insensitive unique indexes for Tutor/Client/LeadSource names, and append-only Lead status history. It backfills one initial event per existing Lead. It deliberately stops if active duplicate names exist; resolve those duplicates on a reviewed copy before applying. Run after 0001–0005.

Migration `0007_commission_modes.sql` stores fixed/manual/percentage/subscription commission terms on each Assignment and updates the finance view. Percentage mode uses the configured percentage of completed paid lesson earnings. Subscription commission accrues immediately from the agreed amount and stores the purchase date; other modes retain the fourth paid lesson threshold. As with 0005, it drops/recreates only the derived finance view because its output types change; no CASCADE is used. Run after 0001–0006.

Migration `0008_commission_accrual_ledger.sql` adds an append-only ledger for subscription, per-lesson percentage, threshold and closure accruals; backfills existing obligations and makes `assignment_finances` read from the ledger. It preserves adjustments as the final closed amount and does not remove Payments or historical Lessons. Run after 0001–0007.

Migration `0009_adjustments_and_payment_refunds.sql` adds immutable PaymentRefund records and changes the finance view to calculate net paid commission. It lets an explicit AssignmentAdjustment change the current commission while preserving the agreed snapshot and all prior payments. Refunds are limited by both outstanding overpayment and the unrefunded amount of the source payment. Run after 0001–0008.

Migration `0010_postgres_fsm_storage.sql` adds persistent PostgreSQL-backed aiogram FSM state/data, so forms and operation keys survive restarts. Configure `FSM_STORAGE=postgres` (default) or explicitly use `memory` for disposable testing. Run after 0001–0009.

Migration `0011_daily_debt_reminders.sql` records one daily reminder per administrator to prevent duplicate sends after restart. The bot sends a concise overdue-debt summary at `DEBT_REMINDER_TIME` in `TIMEZONE` (default 10:00 Europe/Moscow); set `DEBT_REMINDERS_ENABLED=false` to disable it. Run after 0001–0010.

Migration `0012_google_sheets_sync_log.sql` adds an append-only diagnostic log for Sheets sync results. Run after 0001–0011. It does not contain exported rows or credentials. Google Sheets is a one-way analytical projection; only the dedicated columns defined in `bot/integrations/google_sheets.py` are updated/cleared. Manual sync is available to admins; automatic full snapshots are opt-in with `GOOGLE_SHEETS_SYNC_ENABLED=true` and repeat at `GOOGLE_SHEETS_SYNC_INTERVAL` seconds (default 300). A service account and a spreadsheet shared with it are required. The migration has no API side effects; live sync outcomes are documented in `docs/AUDIT_REPORT.md`.

Migration `0013_tutor_payment_batches.sql` adds one parent receipt (`payment_batches`) per actual amount received and links each existing or new `payments` row as an assignment allocation. Existing rows are backfilled one-to-one with the same amount/date/notes, preserving their IDs, refunds, and operation keys. The migration adds a non-null FK and a unique batch/assignment index after checking that every historical payment was linked. It is additive and transactional; verify it on a disposable copy before rollout. Payment totals in the application and Sheets remain the sum of allocation rows, so a batch is not double-counted. Apply after 0001–0012.

Migrations 0001–0012 were exercised in order on 2026-11-27 against a disposable PostgreSQL 17 container with tmpfs storage, starting from a synthetic legacy schema and payment/assignment rows. All completed; legacy finance rows were retained under `assignment_finances_legacy_0001`, Lead status history was backfilled, and foreign keys, checks and indexes were inspected. 0005 and 0007 were corrected to drop/recreate the derived finance view when its column types change. Negative inserts for duplicate active tutor, invalid completed paid Lesson, non-positive Payment, and invalid Lead status were rejected. The source database was not used.

On 2026-11-27, 0013 was applied after 0001–0012 on the disposable populated database; a legacy payment was linked one-to-one and retained. A separate empty disposable database was initialized from current ORM models, then 0013 ran successfully without duplicating its explicit payment-batch FK or unique index. A synthetic payment batch spanning two assignments was checked through the service, repeat operation key, finance view, analytics, tutor history, and Sheets snapshot. No Google API write or source-database mutation was part of this check.
