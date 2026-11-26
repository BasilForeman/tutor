# Database migrations

Apply numbered SQL migrations in order, using a migration table/tracker in the deployment process. `0001_leads_and_assignment_link.sql` is transactional and additive. It preserves old assignments by creating one synthetic historical lead per legacy assignment before adding the required foreign key. If `assignment_finances` is an earlier table/materialized view, the migration renames it to `assignment_finances_legacy_0001` (retaining its rows) before creating the application-facing view from assignments and payments; compare that retained snapshot before a later manual cleanup.

Before applying, inspect the target database and take a restorable backup. Apply only to a confirmed local/test database first, inspect the resulting rows and constraints, then plan any production rollout separately. This repository does not yet include an Alembic runner or automated migration tracking; do not rerun a numbered migration blindly. The SQL is idempotent for schema additions, but the project still needs a migration ledger before repeatable deployment automation.


Migration `0002_payment_idempotency.sql` adds a nullable operation key to historical payments and a partial unique index. Existing payment records remain unchanged. Apply it after migration 0001 on a verified test database.


Migration `0003_lessons.sql` adds the lesson ledger (trial/paid, completed/cancelled), its Assignment foreign key, amount constraint and idempotency key. Existing tables are left intact.

Migration `0004_assignment_idempotency.sql` adds a nullable unique operation key. A new key allows an intentional repeated assignment; replays of the same FSM operation return the original record. Historical assignments retain a NULL key.

Migration `0005_short_term_commission.sql` stores the agreed rate multiplier and closure fields, creates append-only adjustment history, and replaces `assignment_finances` with a view that accrues long-term commission after the configured paid-lesson threshold (default 4). Closing after no more than the configured limit settles at 25% of actual completed paid lesson earnings; the original agreed amount remains intact and the difference is recorded as an adjustment. The view can show a negative remaining amount when a refund is due; refund payment entry is not implemented yet.
