from __future__ import annotations
from typing import Optional

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
    Text,
    func,
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
    nickname: Mapped[str] = mapped_column(String, nullable=False)
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
    name: Mapped[str] = mapped_column(String, nullable=False)

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="source"
    )


class Assignment(Base):
    __tablename__ = "assignments"

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
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="assignment"
    )


class Payment(Base):
    __tablename__ = "payments"

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
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )

    assignment: Mapped["Assignment"] = relationship(
        back_populates="payments"
    )


class AssignmentFinance(Base):
    __tablename__ = "assignment_finances"

    assignment_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    commission_amount: Mapped[Decimal] = mapped_column(
        Numeric,
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric,
    )
    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric,
    )
