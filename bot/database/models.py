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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tutor(Base):
    __tablename__ = "tutors"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    nickname: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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

Index(
    "uq_adjustments_operation_key",
    AssignmentAdjustment.operation_key,
    unique=True,
)
