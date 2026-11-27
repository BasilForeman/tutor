from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FSMState(Base):
    __tablename__ = "fsm_states"

    bot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)
    business_connection_id: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    destiny: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class DebtReminderLog(Base):
    __tablename__ = "debt_reminder_log"

    admin_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reminder_date: Mapped[date] = mapped_column(Date, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class Tutor(Base):
    __tablename__ = "tutors"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    nickname: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="tutor"
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    nickname: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    contact: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="client"
    )



class LeadSource(Base):
    __tablename__ = "lead_sources"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="source"
    )


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("rate > 0", name="ck_assignments_rate_positive"),
        CheckConstraint("commission_amount >= 0", name="ck_assignments_commission_nonnegative"),
        CheckConstraint("commission_multiplier > 0", name="ck_assignments_multiplier_positive"),
        CheckConstraint("short_term_lesson_limit > 0", name="ck_assignments_short_term_limit_positive"),
        CheckConstraint("commission_mode IN ('rate_multiplier', 'fixed', 'manual', 'subscription', 'percent')", name="ck_assignments_commission_mode"),
        CheckConstraint("commission_mode <> 'subscription' OR subscription_purchase_date IS NOT NULL", name="ck_assignments_subscription_purchase_date"),
        CheckConstraint("commission_mode <> 'percent' OR (commission_percentage > 0 AND commission_percentage <= 100)", name="ck_assignments_commission_percentage"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    assignment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    tutor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tutors.id"),
        nullable=False,
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clients.id"),
        nullable=False,
    )
    lead_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leads.id", name="fk_assignments_lead_id_leads"),
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lead_sources.id"),
        nullable=False,
    )
    assigned_by: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric,
        nullable=False,
    )
    commission_amount: Mapped[Decimal] = mapped_column(
        Numeric,
        nullable=False,
    )
    payment_due_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )
    operation_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    commission_multiplier: Mapped[Decimal] = mapped_column(
        Numeric, nullable=False, server_default="4"
    )
    commission_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="rate_multiplier"
    )
    commission_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    subscription_purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    short_term_lesson_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="4"
    )
    is_closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    close_operation_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )

    tutor: Mapped["Tutor"] = relationship(
        back_populates="assignments"
    )
    client: Mapped["Client"] = relationship(
        back_populates="assignments"
    )
    source: Mapped["LeadSource"] = relationship(
        back_populates="assignments"
    )
    lead: Mapped["Lead"] = relationship()
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="assignment"
    )
    commission_accruals: Mapped[list["CommissionAccrual"]] = relationship(
        back_populates="assignment"
    )


Index(
    "uq_assignments_operation_key",
    Assignment.operation_key,
    unique=True,
    postgresql_where=Assignment.operation_key.is_not(None),
)
Index(
    "uq_assignments_close_operation_key",
    Assignment.close_operation_key,
    unique=True,
    postgresql_where=Assignment.close_operation_key.is_not(None),
)
Index("uq_tutors_active_nickname_ci", func.lower(func.btrim(Tutor.nickname)), unique=True,
      postgresql_where=Tutor.is_active.is_(True))
Index("uq_clients_active_nickname_ci", func.lower(func.btrim(Client.nickname)), unique=True,
      postgresql_where=Client.is_active.is_(True))
Index("uq_lead_sources_active_name_ci", func.lower(func.btrim(LeadSource.name)), unique=True,
      postgresql_where=LeadSource.is_active.is_(True))


class TutorPaymentBatch(Base):
    """One actual tutor remittance, optionally split into assignment allocations."""
    __tablename__ = "payment_batches"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_batches_amount_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tutor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tutors.id"), nullable=False, index=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    tutor: Mapped["Tutor"] = relationship()
    allocations: Mapped[list["Payment"]] = relationship(back_populates="batch")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assignments.id"),
        nullable=False,
    )
    payment_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payment_batches.id", name="fk_payments_payment_batch_id"),
        nullable=False,
    )
    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    operation_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )

    assignment: Mapped["Assignment"] = relationship(
        back_populates="payments"
    )
    batch: Mapped["TutorPaymentBatch"] = relationship(back_populates="allocations")
    refunds: Mapped[list["PaymentRefund"]] = relationship(back_populates="payment")


Index("ix_payments_batch_assignment", Payment.payment_batch_id, Payment.assignment_id)


class CommissionAccrual(Base):
    __tablename__ = "commission_accruals"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_commission_accrual_amount_nonnegative"),
        CheckConstraint("event_type IN ('lesson', 'threshold', 'subscription', 'closure')", name="ck_commission_accrual_event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    assignment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("assignments.id"), nullable=False, index=True)
    lesson_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("lessons.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    assignment: Mapped["Assignment"] = relationship(back_populates="commission_accruals")
    lesson: Mapped[Optional["Lesson"]] = relationship()


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_refunds_amount_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    assignment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("assignments.id"), nullable=False, index=True)
    payment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payments.id"), nullable=False, index=True)
    refund_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    payment: Mapped["Payment"] = relationship(back_populates="refunds")





class AssignmentAdjustment(Base):
    __tablename__ = "assignment_adjustments"
    __table_args__ = (
        CheckConstraint("previous_amount >= 0", name="ck_adjustments_previous_nonnegative"),
        CheckConstraint("new_amount >= 0", name="ck_adjustments_new_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assignments.id"), nullable=False, index=True
    )
    previous_amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    new_amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("lesson_type IN ('trial', 'paid')", name="ck_lessons_type"),
        CheckConstraint("status IN ('completed', 'cancelled')", name="ck_lessons_status"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_lessons_amount_nonnegative"),
        CheckConstraint("lesson_type <> 'trial' OR amount IS NULL OR amount = 0", name="ck_lessons_trial_free"),
        CheckConstraint("status <> 'completed' OR lesson_type <> 'paid' OR amount > 0", name="ck_lessons_completed_paid_amount"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assignments.id"), nullable=False, index=True
    )
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    lesson_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operation_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    assignment: Mapped["Assignment"] = relationship()


Index(
    "uq_lessons_operation_key",
    Lesson.operation_key,
    unique=True,
    postgresql_where=Lesson.operation_key.is_not(None),
)
Index("uq_commission_accruals_lesson_id", CommissionAccrual.lesson_id, unique=True,
      postgresql_where=CommissionAccrual.lesson_id.is_not(None))

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id"),
        nullable=False
    )

    source_id: Mapped[int] = mapped_column(
        ForeignKey("lead_sources.id"),
        nullable=False
    )

    subject: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default="new"
    )

    lost_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp()
    )

    client: Mapped["Client"] = relationship()

    source: Mapped["LeadSource"] = relationship()
    status_history: Mapped[list["LeadStatusHistory"]] = relationship(
        back_populates="lead", order_by="LeadStatusHistory.id", cascade="all, delete-orphan"
    )


class LeadStatusHistory(Base):
    __tablename__ = "lead_status_history"
    __table_args__ = (
        CheckConstraint("old_status IN ('new', 'in_progress', 'assigned', 'lost')", name="ck_lead_status_history_old_status"),
        CheckConstraint("new_status IN ('new', 'in_progress', 'assigned', 'lost')", name="ck_lead_status_history_new_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    lead_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leads.id"), nullable=False, index=True)
    old_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    lead: Mapped["Lead"] = relationship(back_populates="status_history")

Index(
    "uq_payments_operation_key",
    Payment.operation_key,
    unique=True,
    postgresql_where=Payment.operation_key.is_not(None),
)

Index(
    "uq_adjustments_operation_key",
    AssignmentAdjustment.operation_key,
    unique=True,
)
