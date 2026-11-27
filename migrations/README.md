# Database migrations

Apply numbered SQL migrations in order, using a migration table/tracker in the deployment process. `0001_leads_and_assignment_link.sql` is transactional and additive. It preserves old assignments by creating one synthetic historical lead per legacy assignment before adding the required foreign key. If `assignment_finances` is an earlier table/materialized view, the migration renames it to `assignment_finances_legacy_0001` (retaining its rows) before creating the application-facing view from assignments and payments; compare that retained snapshot before a later manual cleanup.

Before applying, inspect the target database and take a restorable backup. Apply only to a confirmed local/test database first, inspect the resulting rows and constraints, then plan any production rollout separately. This repository does not yet include an Alembic runner or automated migration tracking; do not rerun a numbered migration blindly. The SQL is idempotent for schema additions, but the project still needs a migration ledger before repeatable deployment automation.


Migration `0002_payment_idempotency.sql` adds a nullable operation key to historical payments and a partial unique index. Existing payment records remain unchanged. Apply it after migration 0001 on a verified test database.


Migration `0003_lessons.sql` adds the lesson ledger (trial/paid, completed/cancelled), its Assignment foreign key, amount constraint and idempotency key. Existing tables are left intact.

Migration `0004_assignment_idempotency.sql` adds a nullable unique operation key. A new key allows an intentional repeated assignment; replays of the same FSM operation return the original record. Historical assignments retain a NULL key.

Migration `0005_short_term_commission.sql` stores the agreed rate multiplier and closure fields, creates append-only adjustment history, and replaces `assignment_finances` with a view that accrues long-term commission after the configured paid-lesson threshold (default 4). Closing after no more than the configured limit settles at 25% of actual completed paid lesson earnings; the original agreed amount remains intact and the difference is recorded as an adjustment. The view can show a negative remaining amount when a refund is due; refund payment entry is not implemented yet. Since PostgreSQL will not change an existing view column's numeric type via `CREATE OR REPLACE VIEW`, this revision drops and recreates only the derived view created by 0001. It does not use `CASCADE`; unexpected dependencies stop the migration safely.

Migration `0006_p0_2_lead_crud_and_history.sql` adds the tutor active flag, active case-insensitive unique indexes for Tutor/Client/LeadSource names, and append-only Lead status history. It backfills one initial event per existing Lead. It deliberately stops if active duplicate names exist; resolve those duplicates on a reviewed copy before applying. Run after 0001–0005.

Migration `0007_commission_modes.sql` stores fixed/manual/percentage/subscription commission terms on each Assignment and updates the finance view. Percentage mode uses the configured percentage of completed paid lesson earnings. Subscription commission accrues immediately from the agreed amount and stores the purchase date; other modes retain the fourth paid lesson threshold. As with 0005, it drops/recreates only the derived finance view because its output types change; no CASCADE is used. Run after 0001–0006.

Migration `0008_commission_accrual_ledger.sql` adds an append-only ledger for subscription, per-lesson percentage, threshold and closure accruals; backfills existing obligations and makes `assignment_finances` read from the ledger. It preserves adjustments as the final closed amount and does not remove Payments or historical Lessons. Run after 0001–0007.

Migration `0009_adjustments_and_payment_refunds.sql` adds immutable PaymentRefund records and changes the finance view to calculate net paid commission. It lets an explicit AssignmentAdjustment change the current commission while preserving the agreed snapshot and all prior payments. Refunds are limited by both outstanding overpayment and the unrefunded amount of the source payment. Run after 0001–0008.

Migration `0010_postgres_fsm_storage.sql` adds persistent PostgreSQL-backed aiogram FSM state/data, so forms and operation keys survive restarts. Configure `FSM_STORAGE=postgres` (default) or explicitly use `memory` for disposable testing. Run after 0001–0009.

Migration `0011_daily_debt_reminders.sql` records one daily reminder per administrator to prevent duplicate sends after restart. The bot sends a concise overdue-debt summary at `DEBT_REMINDER_TIME` in `TIMEZONE` (default 10:00 Europe/Moscow); set `DEBT_REMINDERS_ENABLED=false` to disable it. Run after 0001–0010.

Migration `0012_google_sheets_sync_log.sql` adds an append-only diagnostic log for Sheets sync results. Run after 0001–0011. It does not contain exported rows or credentials. Google Sheets is a one-way analytical projection; only the dedicated columns defined in `bot/integrations/google_sheets.py` are updated/cleared. Manual sync is available to admins; automatic full snapshots are opt-in with `GOOGLE_SHEETS_SYNC_ENABLED=true` and repeat at `GOOGLE_SHEETS_SYNC_INTERVAL` seconds (default 300). A service account and a spreadsheet shared with it are required. No Google API call has been run as part of local tests.

Migrations 0001–0012 were exercised in order on 2026-11-27 against a disposable PostgreSQL 17 container with tmpfs storage, starting from a synthetic legacy schema and payment/assignment rows. All completed; legacy finance rows were retained under `assignment_finances_legacy_0001`, Lead status history was backfilled, and foreign keys, checks and indexes were inspected. 0005 and 0007 were corrected to drop/recreate the derived finance view when its column types change. Negative inserts for duplicate active tutor, invalid completed paid Lesson, non-positive Payment, and invalid Lead status were rejected. The source database was not used.
