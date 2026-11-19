import os, uuid, secrets
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, inspect, text
from rapidfuzz import fuzz

from .database import Base, engine, get_db, SessionLocal
from .models import User, Room, Ticket, Report, TicketHistory, TicketComment, Attachment, DuplicateMatch
from .schemas import (
    LoginIn,
    TokenOut,
    TicketOut,
    RoomIn,
    CommentIn,
    CompleteTicketIn,
    ReopenTicketIn,
    UserIn,
    UserUpdateIn,
    UserPasswordIn,
    UserStatusIn,
    UserDiscordIn,
    DiscordMetadataIn,
)
from .security import hash_password, verify_password, create_token, current_user, worker_or_admin, admin_only

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="RoomTask API", version="0.1.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def migrate_ticket_merge():
    inspector = inspect(engine)
    columns = [column["name"] for column in inspector.get_columns("tickets")]

    if "merged_into_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE tickets ADD COLUMN merged_into_id INTEGER NULL"
            ))
            conn.execute(text(
                "CREATE INDEX ix_tickets_merged_into_id ON tickets (merged_into_id)"
            ))
            conn.execute(text(
                "ALTER TABLE tickets ADD CONSTRAINT fk_tickets_merged_into "
                "FOREIGN KEY (merged_into_id) REFERENCES tickets(id)"
            ))

def migrate_ticket_discord():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("tickets")}

    discord_columns = [
        "discord_channel_id",
        "discord_message_id",
        "discord_thread_id",
        "discord_report_channel_id",
        "discord_report_message_id",
    ]

    with engine.begin() as conn:
        for column in discord_columns:
            if column not in columns:
                conn.execute(text(
                    f"ALTER TABLE tickets ADD COLUMN {column} VARCHAR(32) NULL"
                ))
                print(f"Database migration: added tickets.{column}")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    migrate_ticket_merge()
    migrate_ticket_discord()
    with SessionLocal() as db:
        if not db.query(User).filter_by(role="admin").first():
            username = os.getenv("ADMIN_USERNAME", "admin")
            password = os.getenv("ADMIN_PASSWORD", "")
            if not password or password == "CHANGE_THIS_ADMIN_PASSWORD":
                print("WARNING: Set ADMIN_PASSWORD before production. Initial admin not created.")
            else:
                db.add(User(username=username, password_hash=hash_password(password), role="admin"))
                db.commit()

def log(db, ticket_id, action, actor="system", user_id=None, details=None):
    db.add(TicketHistory(ticket_id=ticket_id, action=action, actor_label=actor, actor_user_id=user_id, details=details))

def ticket_to_out(t: Ticket, db: Session):
    dupes = db.query(DuplicateMatch).filter_by(candidate_ticket_id=t.id, decision="pending").all()
    return TicketOut(
        id=t.id, type=t.type, title=t.title, description=t.description,
        room=t.room.name if t.room else None, status=t.status,
        assigned_to=t.assignee.username if t.assignee else None,
        created_at=t.created_at.isoformat(), completed_at=t.completed_at.isoformat() if t.completed_at else None,
        report_count=len(t.reports),
        duplicate_candidates=[{"report_id": d.report_id, "score": d.score} for d in dupes]
    )

def create_report(db, kind, room_id, description, title, source="web", discord_id=None, reporter_label=None):
    room = db.get(Room, room_id) if room_id else None
    if room_id and (not room or not room.active):
        raise HTTPException(400, "Okänt eller inaktivt rum")

    normalized = " ".join(description.lower().split())
    candidates = db.query(Ticket).filter(
            Ticket.type == kind,
            Ticket.status.in_(["new", "in_progress", "done"]),
            Ticket.merged_into_id.is_(None)
                ).order_by(Ticket.created_at.desc()).limit(150).all()

    matches = []

    for t in candidates:
        if room_id != t.room_id:
            continue

        score = fuzz.WRatio(normalized, " ".join(t.description.lower().split()))        
        if score >= 50:
            matches.append((score, t))



    # Keep each submission as a separate report. A strong candidate is flagged for admin review,
    # but it is NOT automatically merged.
    ticket = Ticket(type=kind, title=title[:180], description=description, room_id=room_id, status="new")
    db.add(ticket)
    db.flush()
    report = Report(ticket_id=ticket.id, source=source, reporter_discord_id=discord_id,
                    reporter_label=reporter_label, original_description=description)
    db.add(report)
    db.flush()
    for score, candidate in matches[:5]:
        db.add(DuplicateMatch(report_id=report.id, candidate_ticket_id=candidate.id, score=score))
    log(db, ticket.id, "report_created", "system", details=f"source={source}; report_id={report.id}")
    if matches:
        log(db, ticket.id, "possible_duplicate_detected", "system",
            details="; ".join(f"ticket={t.id},score={s}" for s,t in matches[:5]))
    return ticket, report, matches

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/internal/discord/board")
def discord_board(x_roomtask_board_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Internal read-only board feed for the Discord bot. Protected by a shared secret."""
    expected = os.getenv("DISCORD_BOARD_API_KEY", "").strip()
    if not expected or not x_roomtask_board_key or not secrets.compare_digest(x_roomtask_board_key, expected):
        raise HTTPException(401, "Unauthorized")

    statuses = ("new", "in_progress", "done")
    result = {"updated_at": datetime.now(timezone.utc).isoformat(), "columns": {}}
    for status in statuses:
        query = db.query(Ticket).filter(
            Ticket.status == status,
            Ticket.merged_into_id.is_(None)
        ).order_by(
            Ticket.completed_at.desc() if status == "done" else Ticket.created_at.desc()
        )
        total = query.count()
        tickets = query.limit(12).all()
        result["columns"][status] = {
            "total": total,
            "tickets": [{
                "id": t.id,
                "title": t.title,
                "room": t.room.name if t.room else "Okänd plats",
                "assigned_to": t.assignee.username if t.assignee else None,
                "type": t.type,
            } for t in tickets],
        }
    return result


        
def discord_bot_user(
    x_roomtask_bot_key: str | None = Header(default=None, alias="X-RoomTask-Bot-Key"),
    x_discord_user_id: str | None = Header(default=None, alias="X-Discord-User-ID"),
    db: Session = Depends(get_db),
    ) -> User:
    expected = os.getenv("DISCORD_BOT_API_KEY", "").strip()

    if (
    not expected
    or not x_roomtask_bot_key
    or not secrets.compare_digest(x_roomtask_bot_key, expected)
    ):
        raise HTTPException(401, "Unauthorized")

    if not x_discord_user_id or not x_discord_user_id.isdigit():
        raise HTTPException(401, "Invalid Discord user")

    if not 17 <= len(x_discord_user_id) <= 20:
        raise HTTPException(401, "Invalid Discord user")

    user = db.query(User).filter_by(discord_id=x_discord_user_id).first()

    if not user or not user.active:
        raise HTTPException(403, "Discord account is not linked to an active RoomTask user")

    return user

@app.post("/api/internal/discord/tickets/{ticket_id}/claim")
def discord_claim_ticket(
    ticket_id: int,
    user: User = Depends(discord_bot_user),
    db: Session = Depends(get_db),
):
    if user.role != "worker":
        raise HTTPException(403, "Only workers can claim tasks")

    db.execute(
        select(User).where(User.id == user.id).with_for_update()
    ).scalar_one()

    active = db.query(Ticket).filter(
        Ticket.assigned_to == user.id,
        Ticket.status == "in_progress"
    ).first()

    if active:
        raise HTTPException(409, f"You already have an active task (#{active.id})")

    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    if ticket.status != "new" or ticket.assigned_to is not None:
        raise HTTPException(409, "Ticket is no longer available")

    ticket.assigned_to = user.id
    ticket.status = "in_progress"

    log(db, ticket.id, "claimed", user.username, user.id)
    db.commit()

    return {"ok": True, "ticket_id": ticket.id}


@app.post("/api/internal/discord/tickets/{ticket_id}/complete")
def discord_complete_ticket(
    ticket_id: int,
    data: CompleteTicketIn,
    user: User = Depends(discord_bot_user),
    db: Session = Depends(get_db),
):
    description = data.completion_description.strip()

    if not description:
        raise HTTPException(400, "Completion description is required")

    ticket = db.get(Ticket, ticket_id)

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    if ticket.status != "in_progress":
        raise HTTPException(409, "Ticket is not in progress")

    if user.role != "admin" and ticket.assigned_to != user.id:
        raise HTTPException(403, "You can only complete your own task")

    ticket.status = "done"
    ticket.completed_at = datetime.now(timezone.utc)

    log(
        db,
        ticket.id,
        "completed",
        user.username,
        user.id,
        details=f"Work completed: {description}"
    )

    db.commit()

    return {"ok": True, "ticket_id": ticket.id}


@app.get("/api/internal/discord/tickets/{ticket_id}")
def discord_ticket_details(
    ticket_id: int,
    user: User = Depends(discord_bot_user),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    comments = db.query(TicketComment).filter_by(
        ticket_id=ticket_id
    ).order_by(TicketComment.created_at.desc()).limit(10).all()

    history = db.query(TicketHistory).filter_by(
        ticket_id=ticket_id
    ).order_by(TicketHistory.created_at.desc()).limit(10).all()

    return {
        "ticket": ticket_to_out(ticket, db).model_dump(),
        "discord": {
            "channel_id": ticket.discord_channel_id,
            "message_id": ticket.discord_message_id,
            "thread_id": ticket.discord_thread_id,
            "report_channel_id": ticket.discord_report_channel_id,
            "report_message_id": ticket.discord_report_message_id,
        },
        "comments": [
            {
                "username": db.get(User, c.user_id).username,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ],
        "history": [
            {
                "actor": h.actor_label,
                "action": h.action,
                "details": h.details,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ],
    }


@app.patch("/api/internal/discord/tickets/{ticket_id}/metadata")
def discord_update_ticket_metadata(
    ticket_id: int,
    data: DiscordMetadataIn,
    x_roomtask_bot_key: str | None = Header(default=None, alias="X-RoomTask-Bot-Key"),
    db: Session = Depends(get_db),
):
    expected = os.getenv("DISCORD_BOT_API_KEY", "").strip()

    if (
        not expected
        or not x_roomtask_bot_key
        or not secrets.compare_digest(x_roomtask_bot_key, expected)
    ):
        raise HTTPException(401, "Unauthorized")

    ticket = db.get(Ticket, ticket_id)

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(ticket, field, value)

    db.commit()

    return {"ok": True, "ticket_id": ticket.id}


@app.post("/api/internal/discord/tickets/{ticket_id}/comments")
def discord_add_comment(
    ticket_id: int,
    data: CommentIn,
    user: User = Depends(discord_bot_user),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    body = data.body.strip()

    if not body:
        raise HTTPException(400, "Comment cannot be empty")

    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=user.id,
        body=body
    )

    db.add(comment)

    log(
        db,
        ticket.id,
        "comment_added",
        user.username,
        user.id
    )

    db.commit()

    return {
        "ok": True,
        "ticket_id": ticket.id,
        "comment_id": comment.id
    }

@app.post("/api/internal/discord/tickets/{ticket_id}/reopen")
def discord_reopen_ticket(
    ticket_id: int,
    data: ReopenTicketIn,
    user: User = Depends(discord_bot_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(403, "Only administrators can reopen tasks")

    reason = data.reason.strip()
    if not reason:
        raise HTTPException(422, "A reopening reason is required")

    ticket = db.get(Ticket, ticket_id)

    if not ticket or ticket.merged_into_id is not None:
        raise HTTPException(404, "Ticket not found")

    if ticket.status != "done":
        raise HTTPException(409, "Task is not completed")

    ticket.status = "in_progress"
    ticket.completed_at = None

    log(
        db,
        ticket.id,
        "reopened_after_admin_discussion",
        user.username,
        user.id,
        details=f"Task reopened by an administrator. Reason: {reason}"
    )

    db.commit()

    return {
        "ok": True,
        "ticket_id": ticket.id,
    }


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Fel användarnamn eller lösenord")

    if not user.active:
        raise HTTPException(
            403,
            "Ditt konto har inaktiverats. Kontakta din administratör."
        )

    return TokenOut(access_token=create_token(user), role=user.role)

@app.get("/api/auth/me")
def me(user: User = Depends(worker_or_admin)):
    return {"id": user.id, "username": user.username, "role": user.role}

@app.get("/api/rooms")
def rooms(db: Session = Depends(get_db)):
    return [{"id": r.id, "name": r.name} for r in db.query(Room).filter_by(active=True).order_by(Room.name).all()]


@app.get("/api/public/rooms/{qr_token}")
def public_room_by_qr(qr_token: str, db: Session = Depends(get_db)):
    room = db.query(Room).filter_by(qr_token=qr_token, active=True).first()
    if not room:
        raise HTTPException(404, "Okänt eller inaktivt rum")
    return {"id": room.id, "name": room.name}

@app.post("/api/public/reports")
async def public_report(
    request: Request,
    kind: str = Form(...),
    room_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db)
):
    if kind not in ("fault", "request"):
        raise HTTPException(400, "Ogiltig ärendetyp")
    if len(title.strip()) < 3 or len(description.strip()) < 5:
        raise HTTPException(400, "Rubrik eller beskrivning är för kort")
    # Simple per-IP throttle; use a proper reverse-proxy/API rate limiter in production.
    ticket, report, matches = create_report(db, kind, room_id, description.strip(), title.strip())
    for upload in files[:4]:
        if upload.content_type not in ALLOWED_TYPES:
            raise HTTPException(400, "Endast JPG, PNG och WebP tillåts")
        content = await upload.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "Bilden är större än tillåten maxstorlek")
        stored = f"{uuid.uuid4().hex}{Path(upload.filename or 'image').suffix.lower()[:10]}"
        (UPLOAD_DIR / stored).write_bytes(content)
        db.add(Attachment(ticket_id=ticket.id, report_id=report.id, stored_name=stored,
                          original_name=(upload.filename or "bild")[:255],
                          content_type=upload.content_type, size=len(content)))
    db.commit()

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            import httpx

            room_name = ticket.room.name if ticket.room else "Okänd plats"
            kind_name = "Felanmälan" if ticket.type == "fault" else "Önskemål"

            message = (
                f"🔔 **Nytt ärende i RoomTask #{ticket.id}**\n"
                f"**Typ:** {kind_name}\n"
                f"**Rum:** {room_name}\n"
                f"**Rubrik:** {ticket.title}\n"
                f"**Beskrivning:** {ticket.description[:1000]}"
            )

            httpx.post(
                webhook,
                json={
                    "content": message,
                    "allowed_mentions": {"parse": []}
                },
                timeout=5.0,
            ).raise_for_status()

        except Exception as exc:
            print(f"Discord new ticket notification failed for ticket #{ticket.id}: {exc}")

    return {"ticket_id": ticket.id, "report_id": report.id, "status": ticket.status,}

@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(status: str | None = None, kind: str | None = None,
                 user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    q = db.query(Ticket).filter(Ticket.merged_into_id.is_(None))
    if status: q = q.filter(Ticket.status == status)
    if kind: q = q.filter(Ticket.type == kind)
    return [ticket_to_out(t, db) for t in q.order_by(Ticket.created_at.desc()).all()]

@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ärendet finns inte")
    return ticket_to_out(t, db)

@app.get("/api/tickets/{ticket_id}/details")
def ticket_details(
    ticket_id: int,
    user: User = Depends(worker_or_admin),
    db: Session = Depends(get_db)
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ärendet finns inte")

    reports = db.query(Report).filter_by(
        ticket_id=ticket_id
    ).order_by(Report.created_at.asc()).all()

    attachments = db.query(Attachment).filter_by(
        ticket_id=ticket_id
    ).order_by(Attachment.created_at.asc()).all()

    return {
        "reports": [
            {
                "id": report.id,
                "source": report.source,
                "reporter": report.reporter_label,
                "created_at": report.created_at.isoformat(),
                "description": report.original_description,
                "attachments": [
                    {
                        "id": attachment.id,
                        "name": attachment.original_name,
                        "content_type": attachment.content_type,
                    }
                    for attachment in attachments
                    if attachment.report_id == report.id
                ],
            }
            for report in reports
        ]
    }

@app.post("/api/tickets/{ticket_id}/claim")
def claim(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    if user.role != "worker":
        raise HTTPException(403, "Endast workers tar vanliga uppdrag")
    # Lock worker row so two simultaneous claim requests for this user cannot both pass.
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    active = db.query(Ticket).filter(Ticket.assigned_to == user.id, Ticket.status == "in_progress").first()
    if active:
        raise HTTPException(409, f"Du har redan ett aktivt uppdrag (#{active.id})")
    t = db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).scalar_one_or_none()
    if not t: raise HTTPException(404, "Ärendet finns inte")
    if t.status != "new" or t.assigned_to is not None:
        raise HTTPException(409, "Ärendet är inte längre tillgängligt")
    t.assigned_to = user.id
    t.status = "in_progress"
    log(db, t.id, "claimed", user.username, user.id)
    db.commit()
    return {"ok": True, "ticket_id": t.id}


@app.post("/api/tickets/{ticket_id}/complete")
def complete(
    ticket_id: int,
    data: CompleteTicketIn,
    user: User = Depends(worker_or_admin),
    db: Session = Depends(get_db)
):
    description = data.completion_description.strip()

    if not description:
        raise HTTPException(400, "Du måste beskriva vad som har gjorts")

    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(404, "Ärendet finns inte")
    if t.status != "in_progress":
        raise HTTPException(409, "Ärendet pågår inte")
    if user.role != "admin" and t.assigned_to != user.id:
        raise HTTPException(403, "Du kan bara avsluta ditt eget ärende")

    t.status = "done"
    t.completed_at = datetime.now(timezone.utc)

    log(
        db,
        t.id,
        "completed",
        user.username,
        user.id,
        details=f"Åtgärd utförd: {description}"
    )

    db.commit()

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            import httpx
            room_name = t.room.name if t.room else "Okänd plats"
            httpx.post(
                webhook,
                json={"content": f"✅ **RoomTask #{t.id} är klart**\n{t.title} · {room_name}\nAnsvarig: {user.username}"},
                timeout=5.0,
            ).raise_for_status()
        except Exception as exc:
            print(f"Discord completion notification failed for ticket #{t.id}: {exc}")

    return {"ok": True}

@app.post("/api/tickets/{ticket_id}/reopen")
def reopen_ticket(
    ticket_id: int,
    user: User = Depends(worker_or_admin),
    db: Session = Depends(get_db)
):
    t = db.get(Ticket, ticket_id)

    if not t:
        raise HTTPException(404, "Ärendet finns inte")

    if t.status != "done":
        raise HTTPException(409, "Ärendet är inte avslutat")

    if user.role != "admin" and t.assigned_to != user.id:
        raise HTTPException(403, "Du kan bara återöppna dina egna ärenden")

    t.status = "in_progress"
    t.completed_at = None

    log(
        db,
        t.id,
        "reopened_after_admin_discussion",
        user.username,
        user.id,
        details="Ärendet återöppnades för fortsatt arbete."
    )

    db.commit()

    return {"ok": True}

@app.post("/api/tickets/{ticket_id}/comments")
def add_comment(ticket_id: int, data: CommentIn, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ärendet finns inte")
    c = TicketComment(ticket_id=t.id, user_id=user.id, body=data.body)
    db.add(c)
    log(db, t.id, "comment_added", user.username, user.id)
    db.commit()
    return {"ok": True, "comment_id": c.id}


@app.put("/api/tickets/{ticket_id}/comments/{comment_id}")
def edit_comment(
    ticket_id: int,
    comment_id: int,
    data: CommentIn,
    user: User = Depends(worker_or_admin),
    db: Session = Depends(get_db)
):
    comment = db.query(TicketComment).filter_by(
        id=comment_id,
        ticket_id=ticket_id
    ).first()

    if not comment:
        raise HTTPException(404, "Kommentaren finns inte")

    if user.role != "admin" and comment.user_id != user.id:
        raise HTTPException(403, "Du får bara redigera dina egna kommentarer")

    old_body = comment.body
    comment.body = data.body

    log(
        db,
        ticket_id,
        "comment_edited",
        user.username,
        user.id,
        f"comment_id={comment.id}\nFöre: {old_body}\nEfter: {data.body}"
    )

    db.commit()
    return {"ok": True}


@app.delete("/api/tickets/{ticket_id}/comments/{comment_id}")
def delete_comment(
    ticket_id: int,
    comment_id: int,
    user: User = Depends(worker_or_admin),
    db: Session = Depends(get_db)
):
    comment = db.query(TicketComment).filter_by(
        id=comment_id,
        ticket_id=ticket_id
    ).first()

    if not comment:
        raise HTTPException(404, "Kommentaren finns inte")

    if user.role != "admin" and comment.user_id != user.id:
        raise HTTPException(403, "Du får bara ta bort dina egna kommentarer")

    log(
        db,
        ticket_id,
        "comment_deleted",
        user.username,
        user.id,
        f"comment_id={comment.id}\nBorttagen kommentar: {comment.body}"
    )

    db.delete(comment)
    db.commit()
    return {"ok": True}

@app.get("/api/tickets/{ticket_id}/history")
def history(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    if not db.get(Ticket, ticket_id): raise HTTPException(404, "Ärendet finns inte")
    rows = db.query(TicketHistory).filter_by(ticket_id=ticket_id).order_by(TicketHistory.created_at).all()
    return [{"id": x.id, "actor": x.actor_label, "action": x.action, "details": x.details,
             "created_at": x.created_at.isoformat()} for x in rows]

@app.get("/api/tickets/{ticket_id}/attachments/{attachment_id}")
def get_attachment(ticket_id: int, attachment_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    a = db.query(Attachment).filter_by(id=attachment_id, ticket_id=ticket_id).first()
    if not a: raise HTTPException(404, "Bilden finns inte")
    return FileResponse(UPLOAD_DIR / a.stored_name, media_type=a.content_type, filename=a.original_name)

@app.post("/api/admin/duplicates/scan")
def scan_duplicates(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(["new", "in_progress", "done"]),
            Ticket.merged_into_id.is_(None)
        )
        .order_by(Ticket.id.asc())
        .all()
    )

    reports = {
        report.ticket_id: report
        for report in db.query(Report).order_by(Report.id.asc()).all()
    }

    created = 0

    for i, older in enumerate(tickets):
        if older.room_id is None:
            continue

        for newer in tickets[i + 1:]:
            if older.room_id != newer.room_id or older.type != newer.type:
                continue

            score = fuzz.WRatio(
                " ".join(older.description.lower().split()),
                " ".join(newer.description.lower().split())
            )

            if score < 50:
                continue

            report = reports.get(newer.id)
            if not report:
                continue

            existing = db.query(DuplicateMatch).filter_by(
                report_id=report.id,
                candidate_ticket_id=older.id
            ).first()

            if existing:
                continue

            db.add(DuplicateMatch(
                report_id=report.id,
                candidate_ticket_id=older.id,
                score=round(score)
            ))

            log(
                db,
                newer.id,
                "possible_duplicate_detected",
                "system",
                details=f"ticket={older.id}; score={round(score)}; source=scan"
            )

            created += 1

    db.commit()

    return {"created": created, "checked_tickets": len(tickets)}

@app.get("/api/admin/duplicates")
def duplicates(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = (
        db.query(DuplicateMatch)
        .filter_by(decision="pending")
        .order_by(DuplicateMatch.score.desc())
        .all()
    )

    result = []

    for match in rows:
        report = db.get(Report, match.report_id)
        if not report:
            continue

        new_ticket = db.get(Ticket, report.ticket_id)
        candidate = db.get(Ticket, match.candidate_ticket_id)

        if new_ticket.merged_into_id is not None or candidate.merged_into_id is not None:
            continue

        if new_ticket.id == candidate.id:
            continue

        result.append({
            "id": match.id,
            "score": match.score,
            "new_ticket": {
                "id": new_ticket.id,
                "title": new_ticket.title,
                "description": new_ticket.description,
                "room": new_ticket.room.name if new_ticket.room else None,
                "status": new_ticket.status,
            },
            "candidate_ticket": {
                "id": candidate.id,
                "title": candidate.title,
                "description": candidate.description,
                "room": candidate.room.name if candidate.room else None,
                "status": candidate.status,
            },
        })

    return result

@app.post("/api/admin/duplicates/{match_id}/decision")
def duplicate_decision(
    match_id: int,
    decision: str = Form(...),
    main_ticket_id: int | None = Form(None),
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    if decision not in ("linked", "rejected"):
        raise HTTPException(400, "Ogiltigt beslut")

    d = db.get(DuplicateMatch, match_id)
    if not d:
        raise HTTPException(404, "Dubblettförslag saknas")

    report = db.get(Report, d.report_id)
    if not report:
        raise HTTPException(404, "Rapporten saknas")

    new_ticket = db.get(Ticket, report.ticket_id)
    candidate = db.get(Ticket, d.candidate_ticket_id)

    if not new_ticket or not candidate:
        raise HTTPException(404, "Ett av ärendena saknas")

    if decision == "rejected":
        d.decision = "rejected"
        d.decided_by = user.id
        log(
            db,
            candidate.id,
            "duplicate_rejected",
            user.username,
            user.id,
            f"match_id={d.id}; report_id={d.report_id}",
        )
        db.commit()
        return {"ok": True}

    if main_ticket_id not in (new_ticket.id, candidate.id):
        raise HTTPException(400, "Ogiltigt huvudärende")

    if new_ticket.id == candidate.id:
        raise HTTPException(400, "Ärendena är redan samma ärende")

    if new_ticket.merged_into_id is not None or candidate.merged_into_id is not None:
        raise HTTPException(409, "Ett av ärendena har redan slagits ihop")

    if new_ticket.type != candidate.type or new_ticket.room_id != candidate.room_id:
        raise HTTPException(400, "Ärendena måste ha samma typ och rum")

    main_ticket = new_ticket if main_ticket_id == new_ticket.id else candidate
    source_ticket = candidate if main_ticket_id == new_ticket.id else new_ticket

    source_id = source_ticket.id
    main_id = main_ticket.id

    db.query(Report).filter(
        Report.ticket_id == source_id
    ).update(
        {Report.ticket_id: main_id},
        synchronize_session=False,
    )

    db.query(TicketHistory).filter(
        TicketHistory.ticket_id == source_id
    ).update(
        {TicketHistory.ticket_id: main_id},
        synchronize_session=False,
    )

    db.query(TicketComment).filter(
        TicketComment.ticket_id == source_id
    ).update(
        {TicketComment.ticket_id: main_id},
        synchronize_session=False,
    )

    db.query(Attachment).filter(
        Attachment.ticket_id == source_id
    ).update(
        {Attachment.ticket_id: main_id},
        synchronize_session=False,
    )

    db.query(DuplicateMatch).filter(
        DuplicateMatch.candidate_ticket_id == source_id,
        DuplicateMatch.decision == "pending",
    ).update(
        {DuplicateMatch.candidate_ticket_id: main_id},
        synchronize_session=False,
    )

    source_ticket.merged_into_id = main_id

    main_ticket.status = "new"
    main_ticket.assigned_to = None
    main_ticket.completed_at = None
    main_ticket.created_at = datetime.now(timezone.utc)

    d.decision = "linked"
    d.decided_by = user.id

    db.flush()

    pending_matches = db.query(DuplicateMatch).filter(
        DuplicateMatch.decision == "pending"
    ).all()

    for match in pending_matches:
        match_report = db.get(Report, match.report_id)
        if match_report and match_report.ticket_id == match.candidate_ticket_id:
            match.decision = "linked"
            match.decided_by = user.id

    log(
        db,
        main_id,
        "tickets_merged",
        user.username,
        user.id,
        f"source_ticket_id={source_id}; match_id={d.id}",
    )

    db.commit()

    return {
        "ok": True,
        "main_ticket_id": main_id,
        "merged_ticket_id": source_id,
    }


@app.get("/api/admin/rooms")
def list_admin_rooms(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "qr_token": r.qr_token,
            "active": r.active
        }
        for r in db.query(Room).order_by(Room.name).all()
    ]

@app.post("/api/admin/rooms")
def create_room(data: RoomIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    room = Room(name=data.name.strip(), qr_token=secrets.token_urlsafe(24))
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "name": room.name, "qr_token": room.qr_token}


@app.get("/api/admin/users")
def list_users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "active": u.active,
            "discord_id": u.discord_id,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@app.post("/api/admin/users")
def create_user(data: UserIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    username = data.username.strip()

    if db.query(User).filter_by(username=username).first():
        raise HTTPException(409, "Användarnamnet finns redan")

    new_user = User(
        username=username,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"ok": True, "id": new_user.id}


@app.put("/api/admin/users/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateIn,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Användaren finns inte")

    username = data.username.strip()
    existing = db.query(User).filter(
        User.username == username,
        User.id != user_id,
    ).first()

    if existing:
        raise HTTPException(409, "Användarnamnet finns redan")

    if target.id == user.id and data.role != "admin":
        raise HTTPException(400, "Du kan inte ändra din egen administratörsroll")

    if target.active and target.role == "admin" and data.role != "admin":
        active_admins = db.query(User).filter_by(
            role="admin",
            active=True,
        ).count()

        if active_admins <= 1:
            raise HTTPException(400, "Den sista aktiva administratören kan inte nedgraderas")

    target.username = username
    target.role = data.role
    db.commit()

    return {"ok": True}


@app.put("/api/admin/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    data: UserPasswordIn,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Användaren finns inte")

    target.password_hash = hash_password(data.password)
    db.commit()

    return {"ok": True}


@app.patch("/api/admin/users/{user_id}/status")
def update_user_status(
    user_id: int,
    data: UserStatusIn,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Användaren finns inte")

    if target.id == user.id and not data.active:
        raise HTTPException(400, "Du kan inte inaktivera ditt eget konto")

    if target.active and not data.active and target.role == "admin":
        active_admins = db.query(User).filter_by(
            role="admin",
            active=True,
        ).count()

        if active_admins <= 1:
            raise HTTPException(400, "Den sista aktiva administratören kan inte inaktiveras")

    target.active = data.active
    db.commit()

    return {"ok": True, "active": target.active}


@app.put("/api/admin/users/{user_id}/discord")
def update_user_discord(
    user_id: int,
    data: UserDiscordIn,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    discord_id = data.discord_id.strip() if data.discord_id else None

    if discord_id:
        if not discord_id.isdigit() or not 17 <= len(discord_id) <= 20:
            raise HTTPException(400, "Invalid Discord ID")

        existing = db.query(User).filter(
            User.discord_id == discord_id,
            User.id != user_id,
        ).first()

        if existing:
            raise HTTPException(409, "Discord account is already linked")

    target.discord_id = discord_id
    db.commit()

    return {"ok": True, "discord_id": target.discord_id}

@app.get("/api/tickets/{ticket_id}/comments")
def comments(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    if not db.get(Ticket, ticket_id):
        raise HTTPException(404, "Ärendet finns inte")

    rows = db.query(TicketComment).filter_by(
        ticket_id=ticket_id
    ).order_by(TicketComment.created_at).all()

    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "username": db.get(User, c.user_id).username,
            "body": c.body,
            "created_at": c.created_at.isoformat()
        }
        for c in rows
    ]
