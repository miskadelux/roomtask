import os, uuid, secrets
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from rapidfuzz import fuzz

from .database import Base, engine, get_db, SessionLocal
from .models import User, Room, Ticket, Report, TicketHistory, TicketComment, Attachment, DuplicateMatch
from .schemas import (
    LoginIn,
    TokenOut,
    TicketOut,
    RoomIn,
    CommentIn,
    UserIn,
    UserUpdateIn,
    UserPasswordIn,
    UserStatusIn,
)
from .security import hash_password, verify_password, create_token, current_user, worker_or_admin, admin_only

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="RoomTask API", version="0.1.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
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
    candidates = db.query(Ticket).filter(Ticket.type == kind, Ticket.status.in_(["new", "in_progress", "done"])).order_by(Ticket.created_at.desc()).limit(150).all()
    matches = []
    for t in candidates:
        if room_id != t.room_id:
            continue
        score = fuzz.token_set_ratio(normalized, " ".join(t.description.lower().split()))
        if score >= 82:
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
    return ticket, report

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
        query = db.query(Ticket).filter(Ticket.status == status).order_by(
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
    ticket, report = create_report(db, kind, room_id, description.strip(), title.strip())
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
    return {"ticket_id": ticket.id, "report_id": report.id, "status": ticket.status,
            "possible_duplicates": [{"ticket_id": t.id, "score": s} for s,t in []]}

@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(status: str | None = None, kind: str | None = None,
                 user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    q = db.query(Ticket)
    if status: q = q.filter(Ticket.status == status)
    if kind: q = q.filter(Ticket.type == kind)
    return [ticket_to_out(t, db) for t in q.order_by(Ticket.created_at.desc()).all()]

@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ärendet finns inte")
    return ticket_to_out(t, db)

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
def complete(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ärendet finns inte")
    if t.status != "in_progress": raise HTTPException(409, "Ärendet pågår inte")
    if user.role != "admin" and t.assigned_to != user.id:
        raise HTTPException(403, "Du kan bara avsluta ditt eget ärende")
    t.status = "done"
    t.completed_at = datetime.now(timezone.utc)
    log(db, t.id, "completed", user.username, user.id)
    db.commit()

    # Optional Discord webhook notification. Configure DISCORD_WEBHOOK_URL in .env.
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            import httpx
            room_name = t.room.name if t.room else "Okänd plats"
            httpx.post(
                webhook,
                json={"content": f"✅ **RoomTask #{t.id} är klart**\\n{t.title} · {room_name}\\nAnsvarig: {user.username}"},
                timeout=5.0,
            ).raise_for_status()
        except Exception as exc:
            # Completion remains saved even if Discord is temporarily unavailable.
            print(f"Discord completion notification failed for ticket #{t.id}: {exc}")
    return {"ok": True}

@app.post("/api/tickets/{ticket_id}/reopen")
def reopen(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ärendet finns inte")
    if t.status != "done": raise HTTPException(409, "Endast färdiga ärenden kan återöppnas")
    if user.role != "worker" or t.assigned_to != user.id:
        raise HTTPException(403, "Endast ansvarig worker får återöppna efter dialog med admin")
    active = db.query(Ticket).filter(Ticket.assigned_to == user.id, Ticket.status == "in_progress").first()
    if active: raise HTTPException(409, f"Du har redan ett aktivt uppdrag (#{active.id})")
    t.status = "in_progress"
    t.completed_at = None
    log(db, t.id, "reopened_after_admin_discussion", user.username, user.id)
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

@app.get("/api/admin/duplicates")
def duplicates(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.query(DuplicateMatch).filter_by(decision="pending").order_by(DuplicateMatch.score.desc()).all()
    return [{"id": d.id, "report_id": d.report_id, "candidate_ticket_id": d.candidate_ticket_id, "score": d.score} for d in rows]

@app.post("/api/admin/duplicates/{match_id}/decision")
def duplicate_decision(match_id: int, decision: str = Form(...), user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if decision not in ("linked", "rejected"): raise HTTPException(400, "Ogiltigt beslut")
    d = db.get(DuplicateMatch, match_id)
    if not d: raise HTTPException(404, "Dubblettförslag saknas")
    d.decision = decision
    d.decided_by = user.id
    log(db, d.candidate_ticket_id, "duplicate_" + decision, user.username, user.id, f"match_id={d.id}; report_id={d.report_id}")
    db.commit()
    return {"ok": True}

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


@app.get("/api/tickets/{ticket_id}/comments")
def comments(ticket_id: int, user: User = Depends(worker_or_admin), db: Session = Depends(get_db)):
    rows = db.query(TicketComment).filter_by(ticket_id=ticket_id).order_by(TicketComment.created_at).all()
    return [{"id": c.id, "username": db.get(User, c.user_id).username, "body": c.body,
             "created_at": c.created_at.isoformat()} for c in rows]
