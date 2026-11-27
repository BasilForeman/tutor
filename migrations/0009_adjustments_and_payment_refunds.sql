-- P1.1: append-only commission corrections and refunds of actual payments.
BEGIN;

CREATE TABLE IF NOT EXISTS payment_refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id),
    payment_id BIGINT NOT NULL REFERENCES payments(id),
    refund_date DATE NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    reason TEXT NOT NULL,
    author VARCHAR(128) NOT NULL,
    operation_key VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_payment_refunds_assignment_id ON payment_refunds(assignment_id);
CREATE INDEX IF NOT EXISTS ix_payment_refunds_payment_id ON payment_refunds(payment_id);

CREATE OR REPLACE VIEW assignment_finances AS
SELECT a.id AS assignment_id,
       COALESCE(latest.new_amount, accrued.amount)::NUMERIC(12,2) AS commission_amount,
       COALESCE(payments.paid_amount, 0::NUMERIC) AS paid_amount,
       COALESCE(latest.new_amount, accrued.amount) - COALESCE(payments.paid_amount, 0::NUMERIC) AS remaining_amount,
       CASE
           WHEN a.commission_mode = 'percent' THEN accrued.amount
           ELSE a.commission_amount
       END::NUMERIC(12,2) AS agreed_commission
FROM assignments AS a
LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(ca.amount), 0::NUMERIC) AS amount
    FROM commission_accruals AS ca
    WHERE ca.assignment_id = a.id
) AS accrued ON TRUE
LEFT JOIN LATERAL (
    SELECT
      (SELECT COALESCE(SUM(p.amount), 0::NUMERIC) FROM payments AS p WHERE p.assignment_id = a.id)
      - (SELECT COALESCE(SUM(r.amount), 0::NUMERIC) FROM payment_refunds AS r WHERE r.assignment_id = a.id)
      AS paid_amount
) AS payments ON TRUE
LEFT JOIN LATERAL (
    SELECT aa.new_amount
    FROM assignment_adjustments AS aa
    WHERE aa.assignment_id = a.id
    ORDER BY aa.id DESC
    LIMIT 1
) AS latest ON TRUE;

COMMIT;
