from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="worker")
    discord_id: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    merged_into_id: Mapped[int | None] = mapped_column(
    ForeignKey("tickets.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(20))  # fault / request
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    discord_channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discord_message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discord_thread_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discord_report_channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discord_report_message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    room = relationship("Room")
    assignee = relationship("User", foreign_keys=[assigned_to])
    reports = relationship("Report", back_populates="ticket")
    attachments = relationship("Attachment", back_populates="ticket")

    __table_args__ = (Index("ix_ticket_status_assignee", "status", "assigned_to"),)

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="web") # web / discord
    reporter_discord_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reporter_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ticket = relationship("Ticket", back_populates="reports")

class TicketHistory(Base):
    __tablename__ = "ticket_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(100), default="system")
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class TicketComment(Base):
    __tablename__ = "ticket_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    uploaded_by: Mapped[str] = mapped_column(String(100), default="public reporter")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ticket = relationship("Ticket", back_populates="attachments")

class DuplicateMatch(Base):
    __tablename__ = "duplicate_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    candidate_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    score: Mapped[int]
    decision: Mapped[str] = mapped_column(String(20), default="pending") # pending/linked/rejected
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
