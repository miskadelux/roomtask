
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
