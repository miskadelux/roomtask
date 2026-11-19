
from pydantic import BaseModel, Field
from typing import Literal


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ReportOut(BaseModel):
    id: int
    ticket_id: int
    source: str
    original_description: str
    created_at: str


class TicketOut(BaseModel):
    id: int
    type: str
    title: str
    description: str
    room: str | None
    status: str
    assigned_to: str | None
    created_at: str
    completed_at: str | None
    report_count: int
    duplicate_candidates: list[dict] = []


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CompleteTicketIn(BaseModel):
    completion_description: str = Field(min_length=1, max_length=4000)


class ReopenTicketIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12)
    role: Literal["admin", "worker"] = "worker"


class UserUpdateIn(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    role: Literal["admin", "worker"]


class UserPasswordIn(BaseModel):
    password: str = Field(min_length=12)


class UserStatusIn(BaseModel):
    active: bool


class UserDiscordIn(BaseModel):
    discord_id: str | None = Field(default=None, min_length=1, max_length=40)

class DiscordMetadataIn(BaseModel):
    discord_channel_id: str | None = Field(default=None, max_length=32)
    discord_message_id: str | None = Field(default=None, max_length=32)
    discord_thread_id: str | None = Field(default=None, max_length=32)
    discord_report_channel_id: str | None = Field(default=None, max_length=32)
    discord_report_message_id: str | None = Field(default=None, max_length=32)

