import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

const API = "";
type AdminRoom = {
    id: number;
    name: string;
    qr_token: string;
    active: boolean;
  };
type Room = {id:number; name:string};
type Ticket = {
  id:number; 
  type:string; 
  title:string; 
  description:string; 
  room:string|null; 
  status:string; 
  assigned_to:string|null; 
  created_at:string; 
  completed_at:string|null; 
  report_count:number; 
  duplicate_candidates:any[]};

type User = {
  id: number;
  username: string;
  role: "admin" | "worker";
  discord_id: string | null;
  active: boolean;
};

type DuplicateMatch = {
  id: number;
  score: number;
  new_ticket: {
    id: number;
    title: string;
    description: string;
    room: string | null;
    created_at: string;
  };
  candidate_ticket: {
    id: number;
    title: string;
    description: string;
    room: string | null;
    status: string;
    created_at: string;
  };
};

function getCommonWords(text1: string, text2: string): Set<string> {
  const words1 = text1.match(/\p{L}[\p{L}\p{N}_-]*/gu) || [];
  const words2 = new Set(
    (text2.match(/\p{L}[\p{L}\p{N}_-]*/gu) || [])
      .map(word => word.toLowerCase())
  );

  return new Set(
    words1
      .map(word => word.toLowerCase())
      .filter(word => words2.has(word))
  );
}

function highlightCommonWords(text: string, common: Set<string>) {
  return text.split(/(\p{L}[\p{L}\p{N}_-]*)/gu).map((part, index) => {
    if (common.has(part.toLowerCase())) {
      return (
        <span
          key={index}
          style={{
            backgroundColor: "#d1fae5",
            color: "#065f46",
            borderRadius: "3px",
            padding: "1px 2px",
          }}
        >
          {part}
        </span>
      );
    }

    return part;
  });
}

function getHistoryAction(action: string): string {
  const labels: Record<string, string> = {
    report_created: "Rapport skapad",
    possible_duplicate_detected: "Möjlig dubblett upptäckt",
    claimed: "Ärende tilldelat",
    completed: "Ärende avslutat",
    reopened_after_admin_discussion: "Ärende återöppnat",
    comment_added: "Kommentar tillagd",
    comment_edited: "Kommentar redigerad",
    comment_deleted: "Kommentar borttagen", 
    tickets_merged: "Ärenden sammanfogade",
  };

  return labels[action] || action;
}

function getHistoryDetails(action: string, details: string | null): string {
  if (!details) return "";

  if (action === "report_created") {
    const reportId = details.match(/report_id=(\d+)/)?.[1];
    const source = details.match(/source=([^;]+)/)?.[1];

    return `Rapport${reportId ? ` #${reportId}` : ""} skickades via ${
      source === "web" ? "webbformuläret" : source || "okänd källa"
    }.`;
  }

  if (action === "possible_duplicate_detected") {
    const matches = [...details.matchAll(/ticket=(\d+),score=([\d.]+)/g)];

    if (matches.length === 0) return "Systemet hittade möjliga dubbletter.";

    return "Liknande ärenden hittades: " +
      matches.map(match =>
        `#${match[1]} (${Number(match[2]).toLocaleString("sv-SE")} % likhet)`
      ).join(", ") + ".";
  }

  if (action === "tickets_merged") {
    const sourceId = details.match(/source_ticket_id=(\d+)/)?.[1];

    return sourceId
      ? `Ärende #${sourceId} slogs ihop med detta ärende.`
      : "Ett annat ärende slogs ihop med detta ärende.";
  }

  if (action === "comment_edited") {
    const commentId = details.match(/comment_id=(\d+)/)?.[1];
    const oldBody = details.match(/Före: ([\s\S]*?)\nEfter: /)?.[1];
    const newBody = details.match(/\nEfter: ([\s\S]*)$/)?.[1];

    return `Kommentar${commentId ? ` #${commentId}` : ""} redigerades.\n` +
      (oldBody !== undefined ? `Tidigare: ${oldBody}\n` : "") +
      (newBody !== undefined ? `Nuvarande: ${newBody}` : "");
  }

  if (action === "comment_deleted") {
    const commentId = details.match(/comment_id=(\d+)/)?.[1];
    const deletedBody = details.match(/Borttagen kommentar: ([\s\S]*)$/)?.[1];

    return `Kommentar${commentId ? ` #${commentId}` : ""} togs bort.` +
      (deletedBody ? ` Innehåll: ${deletedBody}` : "");
  }

  return details;
}


function App() {
  const [users, setUsers] = useState<User[]>([]);
  const [token,setToken] = useState(localStorage.getItem("rt_token") || "");
  const [role,setRole] = useState(localStorage.getItem("rt_role") || "");
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [username,setUsername] = useState("");
  const [password,setPassword] = useState("");
  const [tickets,setTickets] = useState<Ticket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [completingTicket, setCompletingTicket] = useState<Ticket | null>(null);
  const [completionDescription, setCompletionDescription] = useState("");
  const [completionError, setCompletionError] = useState("");
  const [ticketDetails, setTicketDetails] = useState<any>(null);
  const [ticketHistory, setTicketHistory] = useState<any[]>([]);
  const [ticketComments, setTicketComments] = useState<any[]>([]);
  const [newComment, setNewComment] = useState("");
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editingCommentBody, setEditingCommentBody] = useState("");
  const [ticketImages, setTicketImages] = useState<Record<number, string>>({});
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [rooms,setRooms] = useState<Room[]>([]);
  const [adminRooms, setAdminRooms] = useState<AdminRoom[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([]);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword,setNewPassword] = useState("");
  const [newRole,setNewRole] = useState<"admin"|"worker">("worker");
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [kind,setKind] = useState("fault");
  const [roomId,setRoomId] = useState("");
  const [qrRoomToken] = useState(
  new URLSearchParams(window.location.search).get("room") || ""
);

useEffect(() => {
  if (!qrRoomToken) return;

  fetch(`/api/public/rooms/${encodeURIComponent(qrRoomToken)}`)
    .then(async response => {
      if (!response.ok) throw new Error("QR-koden tillhör inget aktivt rum");
      return response.json();
    })
    .then(room => setRoomId(String(room.id)))
    .catch(() => setError("QR-koden är ogiltig eller tillhör ett inaktivt rum."));
}, [qrRoomToken]);
  const [title,setTitle] = useState("");
  const [description,setDescription] = useState("");
  const [uploads,setUploads] = useState<FileList|null>(null);
  const [tab,setTab] = useState<"board"|"public"|"users"|"duplicates"|"rooms">(qrRoomToken ? "public" : "board");  
  
  async function api(path:string, options:RequestInit = {}) {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API}${path}`, {...options, headers});
    if (!response.ok) {
      const data = await response.json().catch(()=>({detail:"Något gick fel"}));
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    return response.status === 204 ? null : response.json();
  }

    async function openTicket(ticket: Ticket) {
    setSelectedTicket(ticket);
    setDetailsLoading(true);
    setTicketDetails(null);
    setTicketHistory([]);
    setTicketComments([]);
    setTicketImages({});
    setError("");

    try {
      const [details, history, comments] = await Promise.all([
        api(`/api/tickets/${ticket.id}/details`),
        api(`/api/tickets/${ticket.id}/history`),
        api(`/api/tickets/${ticket.id}/comments`),
      ]);

      setTicketDetails(details);
      setTicketHistory(history);
      setTicketComments(comments);

      const images: Record<number, string> = {};

      for (const report of details.reports) {
        for (const attachment of report.attachments) {
          const response = await fetch(
            `/api/tickets/${ticket.id}/attachments/${attachment.id}`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
              },
            }
          );

          if (response.ok) {
            const blob = await response.blob();
            images[attachment.id] = URL.createObjectURL(blob);
          }
        }
      }

      setTicketImages(images);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDetailsLoading(false);
    }
  }

  async function addComment() {
  if (!selectedTicket || !newComment.trim()) return;

  setError("");
  setNotice("");

  try {
    await api(`/api/tickets/${selectedTicket.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: newComment.trim() })
    });

    const comments = await api(`/api/tickets/${selectedTicket.id}/comments`);
    const history = await api(`/api/tickets/${selectedTicket.id}/history`);

    setTicketComments(comments);
    setTicketHistory(history);
    setNewComment("");
    setNotice("Kommentaren har lagts till.");
  } catch (e: any) {
    setError(e.message);
  }
}

    async function saveComment(commentId: number) {
    if (!selectedTicket) return;

    setError("");
    setNotice("");

    try {
      await api(`/api/tickets/${selectedTicket.id}/comments/${commentId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: editingCommentBody })
      });

      const comments = await api(`/api/tickets/${selectedTicket.id}/comments`);
      const history = await api(`/api/tickets/${selectedTicket.id}/history`);

      setTicketComments(comments);
      setTicketHistory(history);
      setEditingCommentId(null);
      setEditingCommentBody("");
      setNotice("Kommentaren har uppdaterats.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function deleteComment(commentId: number) {
    if (!selectedTicket) return;

    if (!window.confirm("Vill du verkligen ta bort kommentaren?")) return;

    setError("");
    setNotice("");

    try {
      await api(`/api/tickets/${selectedTicket.id}/comments/${commentId}`, {
        method: "DELETE"
      });

      const comments = await api(`/api/tickets/${selectedTicket.id}/comments`);
      const history = await api(`/api/tickets/${selectedTicket.id}/history`);

      setTicketComments(comments);
      setTicketHistory(history);
      setNotice("Kommentaren har tagits bort.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function load() {
    try {
      const [t,r] = await Promise.all([api("/api/tickets"), fetch("/api/rooms").then(x=>x.json())]);
      setTickets(t); setRooms(r);
    } catch(e:any) { setError(e.message); }
  }
    
  async function loadAdminRooms() {
  try {
    const data = await api("/api/admin/rooms");
    setAdminRooms(data);
  } catch (e: any) {
    setError(e.message);
  }
}

    async function loadUsers() {
      try {
        const data = await api("/api/admin/users");
        setUsers(data);
      } catch (e: any) {
        setError(e.message);
      }
    }
  async function loadDuplicates() {
  setError("");
  setNotice("");

  try {
    const scan = await api("/api/admin/duplicates/scan", {
      method: "POST",
    });

    const data = await api("/api/admin/duplicates");
    setDuplicates(data);

    setNotice(`Sökningen är klar. ${scan.created} nya dubblettförslag hittades.`);
  } catch (e: any) {
    setError(e.message);
  }
}
async function decideDuplicate(
  matchId: number,
  decision: "linked" | "rejected",
  mainTicketId?: number
) {
  setError("");
  setNotice("");

  try {
    const data = new FormData();
    data.append("decision", decision);

    if (mainTicketId !== undefined) {
      data.append("main_ticket_id", String(mainTicketId));
    }

    await api(`/api/admin/duplicates/${matchId}/decision`, {
      method: "POST",
      body: data,
    });

    await loadDuplicates();
    await load();

    setNotice(
      decision === "linked"
        ? `Ärendena har slagits ihop. Huvudärende #${mainTicketId} har behållits.`
        : "Dubblettförslaget har avvisats."
    );
  } catch (e: any) {
    setError(e.message);
  }
}
  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");

    try {
      await api("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: newUsername,
          password: newPassword,
          role: newRole,
        }),
      });

      setNewUsername("");
      setNewPassword("");
      setNewRole("worker");
      await loadUsers();
      setNotice("Användaren har skapats.");
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function updateUser(
    userId: number,
    username: string,
    role: "admin" | "worker"
  ) {
    setError("");
    setNotice("");

    try {
      await api(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, role }),
      });

      await loadUsers();
      setNotice("Användaren har uppdaterats.");
    } catch (e: any) {
      setError(e.message);
    }
  }


    async function updateUserDiscord(userId: number, discordId: string | null) {
      setError("");
      setNotice("");

      try {
        await api(`/api/admin/users/${userId}/discord`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ discord_id: discordId }),
        });

        await loadUsers();
        setNotice("Discord account updated.");
      } catch (e: any) {
        setError(e.message);
      }
    }
  async function resetUserPassword(userId: number, password: string) {
    setError("");
    setNotice("");

    try {
      await api(`/api/admin/users/${userId}/password`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      setNotice("Lösenordet har återställts.");
    } catch (e: any) {
      setError(e.message);
    }
  }




  async function updateUserStatus(userId: number, active: boolean) {
    setError("");
    setNotice("");

    try {
      await api(`/api/admin/users/${userId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active }),
      });

      await loadUsers();
      setNotice(active ? "Kontot har aktiverats." : "Kontot har inaktiverats.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(()=>{ if(token) load(); else fetch("/api/rooms").then(r=>r.json()).then(setRooms).catch(()=>{}); },[token]);

  async function login(e:React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      const r = await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,password})});
      const d=await r.json(); if(!r.ok) throw new Error(d.detail || "Inloggning misslyckades");
      localStorage.setItem("rt_token", d.access_token);
      localStorage.setItem("rt_role", d.role);
      setToken(d.access_token);
      setRole(d.role);

      const me = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${d.access_token}` }
      });

      if (!me.ok) throw new Error("Kunde inte hämta användaruppgifter");

      const currentUser = await me.json();
      setCurrentUserId(currentUser.id);
    } catch(e:any){setError(e.message);}
  }
  async function submitReport(e:React.FormEvent) {
    e.preventDefault(); setError(""); setNotice("");
    const data=new FormData(); data.append("kind",kind); data.append("room_id",roomId); data.append("title",title); data.append("description",description);
    if(uploads) Array.from(uploads).slice(0,4).forEach(f=>data.append("files",f));
    try {
      const r=await fetch("/api/public/reports",{method:"POST",body:data});
      const d=await r.json(); if(!r.ok) throw new Error(d.detail || "Kunde inte skicka");
      setNotice(`Tack! Ärende #${d.ticket_id} har registrerats.`);
      setTitle("");setDescription("");setUploads(null);
    } catch(e:any){setError(e.message);}
  }
  async function action(path:string) {
    setError("");setNotice("");
    try { await api(path,{method:"POST"}); await load(); setNotice("Ärendet uppdaterades."); }
    catch(e:any){setError(e.message);}
  }

async function completeTicket() {
  if (!completingTicket) return;

  if (!completionDescription.trim()) {
    setCompletionError("Du måste skriva vad du har gjort innan du kan skicka.");
    return;
  }

  setCompletionError("");
  setError("");
  setNotice("");

  try {
    await api(`/api/tickets/${completingTicket.id}/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        completion_description: completionDescription.trim()
      })
    });

    setCompletingTicket(null);
    setCompletionDescription("");
    await load();
    setNotice("Ärendet markerades som klart.");
  } catch (e: any) {
    setError(e.message);
  }
}

function logout() {
  localStorage.removeItem("rt_token");
  localStorage.removeItem("rt_role");

  setToken("");
  setRole("");
  setCurrentUserId(null);
  setTickets([]);
  setUsers([]);
  setDuplicates([]);
  setTab("board");
  setError("");
  setNotice("");
}  const columns=[{id:"new",label:"Nytt"},{id:"in_progress",label:"Pågår"},{id:"done",label:"Klart"}];

  return <main className="shell">
    <header><div><div className="eyebrow">ÄRENDEHANTERING</div><h1>RoomTask</h1></div>
    <nav>
      <button
        className={tab === "board" ? "active" : ""}
        onClick={() => setTab("board")}
      >
        Arbetsyta
      </button>

      <button
        className={tab === "public" ? "active" : ""}
        onClick={() => setTab("public")}
      >
        Rapportera
      </button> 

      {token && role === "admin" && (
        <button
          className={tab === "users" ? "active" : ""}
          onClick={() => {
            console.log("Klickade på Användare", { role, token: !!token });
            setTab("users");
            loadUsers();
          }}
        >
          Användare
        </button>
      )}
      {token && role === "admin" && (
        <button
          className={tab === "rooms" ? "active" : ""}
          onClick={() => {
            setTab("rooms");
            loadAdminRooms();
          }}
        >
          QR-koder
        </button>
      )}
      {token && role === "admin" && (
        <button
          className={tab === "duplicates" ? "active" : ""}
          onClick={() => {
            setTab("duplicates");
            loadDuplicates();
          }}
        >
          Dubbletter
        </button>
      )}

      {token && <button onClick={logout}>Logga ut</button>}
    </nav>
    </header>
    {error&&<div className="alert error">{error}</div>}{notice&&<div className="alert success">{notice}</div>}

    {tab==="public" && <section 
    
    
    className="panel narrow"><h2>Skicka in rapport</h2><p className="muted">Du behöver inte ange ditt namn.</p><form onSubmit={submitReport}>
      <label>Typ<select value={kind} onChange={e=>setKind(e.target.value)}><option value="fault">Felanmälan</option><option value="request">Önskemål</option></select></label>
      <label>Rum<select required value={roomId} onChange={e=>setRoomId(e.target.value)}><option value="">Välj rum</option>{rooms.map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select></label>
      <label>Rubrik<input required minLength={3} maxLength={180} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Exempel: Trasig lampa"/></label>
      <label>Beskrivning
        <textarea required minLength={5} value={description} onChange={e=>setDescription(e.target.value)} rows={5} placeholder="Beskriv problemet eller önskemålet..."/></label>
      <label>Bildbevis (max 4 bilder)<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>setUploads(e.target.files)}/></label>
      <button className="primary">Skicka rapport</button>
    </form></section>}

    {tab === "users" && token && role === "admin" && (
      <section className="panel">
        <h2>Användaradministration</h2>
        <p className="muted">Skapa och hantera användarkonton.</p>

        <form onSubmit={createUser}>
          <h3>Skapa användare</h3>

          <label>
            Användarnamn
            <input
              required
              minLength={3}
              maxLength={80}
              value={newUsername}
              onChange={e => setNewUsername(e.target.value)}
            />
          </label>

          <label>
            Lösenord
            <input
              type="password"
              required
              minLength={12}
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
            />
          </label>

          <label>
            Behörighet
            <select
              value={newRole}
              onChange={e => setNewRole(e.target.value as "admin" | "worker")}
            >
              <option value="worker">Worker</option>
              <option value="admin">Administratör</option>
            </select>
          </label>

          <button className="primary">Skapa användare</button>
        </form>

        <h3>Befintliga användare</h3>

        {users.map(u => (
          <article className="ticket" key={u.id}>
            <b>#{u.id} · {u.username}</b>
            <p className="muted">
              Roll: {u.role === "admin" ? "Administratör" : "Worker"}
              {" · "}
              Status: {u.active ? "Aktiv" : "Inaktiv"}
            </p>

            <button
              onClick={() => {
                const username = window.prompt("Nytt användarnamn:", u.username);
                if (username === null) return;

                const role = window.prompt(
                  "Ange roll: admin eller worker",
                  u.role
                );

                if (role !== "admin" && role !== "worker") return;

                updateUser(u.id, username, role);
              }}
            >
              Ändra användare
            </button>
            <button
              onClick={() => {
                const password = window.prompt("Ange nytt lösenord (minst 12 tecken):");
                if (password) resetUserPassword(u.id, password);
              }}
            >
              Återställ lösenord
            </button>

            <button
              onClick={() => {
                const discordId = window.prompt(
                  "Enter Discord User ID (leave empty to unlink):",
                  u.discord_id || ""
                );

                if (discordId === null) return;

                updateUserDiscord(u.id, discordId.trim() || null);
              }}
            >
              {u.discord_id ? "Change Discord account" : "Link Discord account"}
            </button>

            <p className="muted">
              Discord ID: {u.discord_id || "Not linked"}
            </p>
          </article>
    ))}
  </section>
  )}

    {tab === "rooms" && token && role === "admin" && (
  <section className="panel">
    <div className="toolbar">
      <div>
        <h2>QR-koder för rum</h2>
        <p className="muted">
          Skanna QR-koden för att öppna rapportformuläret med rummet förvalt.
        </p>
      </div>
      <button onClick={loadAdminRooms}>Uppdatera</button>
    </div>

    <div className="room-qr-grid">
      {adminRooms.map(room => (
        <article className="ticket" key={room.id}>
          <h3>{room.name}</h3>

          <div className="qr-code">
            <QRCodeSVG
              value={`${window.location.origin}/?room=${encodeURIComponent(room.qr_token)}`}
              size={220}
              level="H"
            />
          </div>

          <p className="muted">
            {room.active ? "Aktivt rum" : "Inaktivt rum"}
          </p>

          <button
            onClick={() => window.open(
              `/?room=${encodeURIComponent(room.qr_token)}`,
              "_blank"
            )}
          >
            Öppna rapportformulär
          </button>
        </article>
      ))}

      {adminRooms.length === 0 && (
        <p className="muted">Inga rum finns registrerade.</p>
      )}
    </div>
  </section>
)}

        {tab === "duplicates" && token && role === "admin" && (
      <section className="panel">
        <div className="toolbar">
          <div>
            <h2>Dubblettgranskning</h2>
            <p className="muted">
              Granska rapporter som systemet har identifierat som möjliga dubbletter.
            </p>
          </div>
          <button onClick={loadDuplicates}>Uppdatera</button>
        </div>

        {duplicates.length === 0 ? (
          <p className="muted">Inga väntande dubblettförslag.</p>
        ) : (
          duplicates.map(match => (
            <article className="ticket" key={match.id}>
              <div className="ticket-top">
                <b>Dubblettförslag #{match.id}</b>
                <span className="tag">
                  Matchning: {match.score} %
                </span>
              </div>

              <div className="board">
                <section className="column">
                  <h3>Nytt ärende #{match.new_ticket.id}</h3>
                  <b>{match.new_ticket.title}</b>
                  <p className="muted">
                    Rum: {match.new_ticket.room || "Okänt rum"}
                  </p>
                  <p>
                    {highlightCommonWords(
                      match.new_ticket.description,
                      getCommonWords(
                        match.new_ticket.description,
                        match.candidate_ticket.description
                      )
                    )}
                  </p>                
                  
                </section>

                <section className="column">
                  <h3>Befintligt ärende #{match.candidate_ticket.id}</h3>
                  <b>{match.candidate_ticket.title}</b>
                  <p className="muted">
                    Rum: {match.candidate_ticket.room || "Okänt rum"}
                  </p>
                  <p>
                    {highlightCommonWords(
                      match.candidate_ticket.description,
                      getCommonWords(
                        match.candidate_ticket.description,
                        match.new_ticket.description
                      )
                    )}
                  </p>
                  <p className="muted">
                    Status: {match.candidate_ticket.status}
                  </p>
                </section>
              </div>

              <div className="actions">
                <button
                  className="primary"
                  onClick={() =>
                    decideDuplicate(match.id, "linked", match.new_ticket.id)
                  }
                >
                  Behåll nytt ärende #{match.new_ticket.id}
                </button>

                <button
                  onClick={() =>
                    decideDuplicate(match.id, "linked", match.candidate_ticket.id)
                  }
                >
                  Behåll befintligt ärende #{match.candidate_ticket.id}
                </button>

                <button
                  onClick={() => decideDuplicate(match.id, "rejected")}
                >
                  Avvisa förslag
                      </button>
                    </div>
                  </article>
                ))
              )}
            </section>
          )}

      {tab === "board" && !token && (
        <section className="panel narrow">
          <h2>Worker-inloggning</h2>
          <p className="muted">
            Den interna arbetsytan kräver ett konto.
          </p>

          <form onSubmit={login}>
            <label>
              Användarnamn
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
              />
            </label>

            <label>
              Lösenord
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </label>

            <button className="primary">Logga in</button>
          </form>
        </section>
      )}

      {tab === "board" && token && (
        <>
          <div className="toolbar">
            <div>
              <h2>Ärenden</h2>
              <p className="muted">Inloggad som {role}</p>
            </div>
            <button onClick={load}>Uppdatera</button>
          </div>

          <div className="board">
            {columns.map(col => (
              <section className="column" key={col.id}>
                <h3>
                  {col.label}
                  <span>
                    {tickets.filter(t => t.status === col.id).length}
                  </span>
                </h3>

                {tickets
                  .filter(t => t.status === col.id)
                  .map(t => (
                    <article
                      className="ticket"
                      key={t.id}
                      onClick={() => openTicket(t)}
                    >
                      <div className="ticket-top">
                        <b>#{t.id} · {t.title}</b>
                        <span className={`tag ${t.type}`}>
                          {t.type === "fault" ? "Fel" : "Önskemål"}
                        </span>
                      </div>

                      <p className="muted">
                        {t.room || "Okänd plats"} · {t.report_count} rapport(er)
                      </p>

                      <p>{t.description}</p>

                      <p className="muted">
                        Ansvarig: {t.assigned_to || "Ingen"}
                      </p>

                      {t.duplicate_candidates.length > 0 && (
                        <p className="warn">
                          Möjlig dubblett finns
                        </p>
                      )}

                      <div
                        className="actions"
                        onClick={e => e.stopPropagation()}
                      >
                        {t.status === "new" && role === "worker" && (
                          <button
                            className="primary"
                            onClick={() => action(`/api/tickets/${t.id}/claim`)}
                          >
                            Ta ärendet
                          </button>
                        )}

                        {t.status === "in_progress" &&
                          (role === "admin" || t.assigned_to) && (
                            <button
                              className="primary"
                              onClick={() => {
                                setCompletingTicket(t);
                                setCompletionDescription("");
                                setError("");
                                setCompletionError("");
                              }}
                            >
                              Markera klart
                            </button>
                          )}

                        {t.status === "done" && role === "worker" && (
                          <button
                            onClick={() => action(`/api/tickets/${t.id}/reopen`)}
                          >
                            Återöppna
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
              </section>
            ))}
          </div>
        </>
      )}

      {selectedTicket && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedTicket(null)}
        >
          <div
            className="ticket-modal"
            onClick={e => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h2>Ärende #{selectedTicket.id}</h2>
                <p className="muted">{selectedTicket.title}</p>
              </div>

              <button onClick={() => setSelectedTicket(null)}>
                ✕
              </button>
            </div>

            {detailsLoading ? (
              <p>Laddar ärende...</p>
            ) : (
              <>
                <section>
                  <h3>Beskrivning</h3>
                  <p>{selectedTicket.description}</p>
                  <p className="muted">
                    Plats: {selectedTicket.room || "Okänd plats"}
                  </p>
                </section>

                <section>
                  <h3>Ursprungliga rapporter</h3>

                  {ticketDetails?.reports?.length ? (
                    ticketDetails.reports.map((report: any) => (
                      <article className="detail-report" key={report.id}>
                        <b>Rapport #{report.id}</b>
                        <p className="muted">
                          {report.reporter || report.source} ·{" "}
                          {new Date(report.created_at).toLocaleString("sv-SE")}
                        </p>
                        <p>{report.description}</p>

                        {report.attachments.map((attachment: any) => (
                          <div key={attachment.id}>
                            {ticketImages[attachment.id] && (
                              <img
                                className="ticket-image"
                                src={ticketImages[attachment.id]}
                                alt={attachment.name}
                              />
                            )}
                            <p className="muted">{attachment.name}</p>
                          </div>
                        ))}
                      </article>
                    ))
                  ) : (
                    <p className="muted">Inga rapporter hittades.</p>
                  )}
                </section>

                <section>
                  <h3>Kommentarer</h3>

                  <div className="comment-form">
                    <textarea
                      value={newComment}
                      onChange={e => setNewComment(e.target.value)}
                      placeholder="Skriv en kommentar..."
                      maxLength={4000}
                      rows={3}
                    />
                    <button
                      onClick={addComment}
                      disabled={!newComment.trim()}
                    >
                      Skicka kommentar
                    </button>
                  </div>

                  {ticketComments.map(comment => {
                    const canManageComment =
                      role === "admin" || comment.user_id === currentUserId;

                    return (
                      <article className="detail-report" key={comment.id}>
                        <b>{comment.username}</b>

                        {editingCommentId === comment.id ? (
                          <>
                            <textarea
                              value={editingCommentBody}
                              onChange={e => setEditingCommentBody(e.target.value)}
                              maxLength={4000}
                              rows={4}
                            />

                            <button
                              onClick={() => saveComment(comment.id)}
                              disabled={!editingCommentBody.trim()}
                            >
                              Spara
                            </button>

                            <button
                              onClick={() => {
                                setEditingCommentId(null);
                                setEditingCommentBody("");
                              }}
                            >
                              Avbryt
                            </button>
                          </>
                        ) : (
                          <>
                            <p>{comment.body}</p>

                            {canManageComment && (
                              <div>
                                <button
                                  onClick={() => {
                                    setEditingCommentId(comment.id);
                                    setEditingCommentBody(comment.body);
                                  }}
                                >
                                  Redigera
                                </button>

                                <button onClick={() => deleteComment(comment.id)}>
                                  Ta bort
                                </button>
                              </div>
                            )}
                          </>
                        )}

                        <p className="muted">
                          {new Date(comment.created_at).toLocaleString("sv-SE")}
                        </p>
                      </article>
                    );
                  })}

                  {ticketComments.length === 0 && (
                    <p className="muted">Inga kommentarer.</p>
                  )}
                </section>

                <section>
                  <h3>Historik</h3>

                  {[...ticketHistory].reverse().map(item => (
                    <article className="detail-history" key={item.id}>
                      <b>
                        {item.actor === "system"
                          ? "Systemet"
                          : item.actor === "admin"
                            ? "Administratör"
                            : item.actor}
                      </b>
                      {" · "}
                      {getHistoryAction(item.action)}

                      {item.details && (
                        <p>
                          {getHistoryDetails(item.action, item.details)}
                        </p>
                      )}

                      <p className="muted">
                        {new Date(item.created_at).toLocaleString("sv-SE")}
                      </p>
                    </article>
                  ))}

                  {ticketHistory.length === 0 && (
                    <p className="muted">Ingen historik.</p>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
      )}

      {completingTicket && (
        <div
          className="modal-backdrop"
          onClick={() => setCompletingTicket(null)}
        >
          <div
            className="ticket-modal"
            onClick={e => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h2>Markera ärende som klart</h2>
                <p className="muted">
                  Ärende #{completingTicket.id}: {completingTicket.title}
                </p>
              </div>

              <button onClick={() => setCompletingTicket(null)}>
                ✕
              </button>
            </div>

            <section>
              <h3>Vad har du gjort?</h3>
              <p className="muted">
                Beskriv åtgärden som utförts. Beskrivningen sparas i ärendets historik.
              </p>

             <textarea
                rows={5}
                maxLength={4000}
                value={completionDescription}
                onChange={e => {
                  setCompletionDescription(e.target.value);
                  setCompletionError("");
                }}
                placeholder="Beskriv vad som har åtgärdats..."
              />

              {completionError && (
                <p className="error">{completionError}</p>
              )}
            </section>

            <div className="actions">
              <button onClick={() => setCompletingTicket(null)}>
                Avbryt
              </button>

              <button
                className="primary"
                onClick={completeTicket}
              >
                Bekräfta och markera klart
              </button>
            </div>
          </div>
        </div>
      )}


  </main>;
}
export default App;
