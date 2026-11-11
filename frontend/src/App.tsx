import { useEffect, useState } from "react";

const API = "";
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
  active: boolean;
  created_at: string;
};


function App() {
  const [token,setToken] = useState(localStorage.getItem("rt_token") || "");
  const [role,setRole] = useState(localStorage.getItem("rt_role") || "");
  const [username,setUsername] = useState("");
  const [password,setPassword] = useState("");
  const [tickets,setTickets] = useState<Ticket[]>([]);
  const [rooms,setRooms] = useState<Room[]>([]);
  const [users,setUsers] = useState<User[]>([]);
  const [newUsername,setNewUsername] = useState("");
  const [newPassword,setNewPassword] = useState("");
  const [newRole,setNewRole] = useState<"admin"|"worker">("worker");
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [kind,setKind] = useState("fault");
  const [roomId,setRoomId] = useState("");
  const [title,setTitle] = useState("");
  const [description,setDescription] = useState("");
  const [uploads,setUploads] = useState<FileList|null>(null);
  const [tab,setTab] = useState<"board"|"public"|"users">("board");

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
  async function load() {
    try {
      const [t,r] = await Promise.all([api("/api/tickets"), fetch("/api/rooms").then(x=>x.json())]);
      setTickets(t); setRooms(r);
    } catch(e:any) { setError(e.message); }
  }
  async function loadUsers() {
    try {
      const data = await api("/api/admin/users");
      setUsers(data);
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
      localStorage.setItem("rt_token",d.access_token); localStorage.setItem("rt_role",d.role);
      setToken(d.access_token); setRole(d.role);
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
function logout() {
  localStorage.removeItem("rt_token");
  localStorage.removeItem("rt_role");

  setToken("");
  setRole("");
  setTickets([]);
  setUsers([]);
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

      {token && <button onClick={logout}>Logga ut</button>}
    </nav>
    </header>
    {error&&<div className="alert error">{error}</div>}{notice&&<div className="alert success">{notice}</div>}

    {tab==="public" && <section 
    
    
    className="panel narrow"><h2>Skicka in rapport</h2><p className="muted">Du behöver inte ange ditt namn.</p><form onSubmit={submitReport}>
      <label>Typ<select value={kind} onChange={e=>setKind(e.target.value)}><option value="fault">Felanmälan</option><option value="request">Önskemål</option></select></label>
      <label>Rum<select required value={roomId} onChange={e=>setRoomId(e.target.value)}><option value="">Välj rum</option>{rooms.map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select></label>
      <label>Rubrik<input required minLength={3} maxLength={180} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Exempel: Trasig lampa"/></label>
      <label>Beskrivning<textarea required minLength={5} value={description} onChange={e=>setDescription(e.target.value)} rows={5} placeholder="Beskriv problemet eller önskemålet..."/></label>
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
              onClick={() => updateUserStatus(u.id, !u.active)}
            >
              {u.active ? "Inaktivera konto" : "Aktivera konto"}
            </button>
          </article>
        ))}
      </section>
    )}

    {tab==="board" && !token && <section className="panel narrow"><h2>Worker-inloggning</h2><p className="muted">Den interna arbetsytan kräver ett konto.</p><form onSubmit={login}><label>Användarnamn<input value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Lösenord<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button className="primary">Logga in</button></form></section>}
    {tab==="board" && token && <><div className="toolbar"><div><h2>Ärenden</h2><p className="muted">Inloggad som {role}</p></div><button onClick={load}>Uppdatera</button></div><div className="board">{columns.map(col=><section className="column" key={col.id}><h3>{col.label}<span>{tickets.filter(t=>t.status===col.id).length}</span></h3>{tickets.filter(t=>t.status===col.id).map(t=><article className="ticket" key={t.id}><div className="ticket-top"><b>#{t.id} · {t.title}</b><span className={`tag ${t.type}`}>{t.type==="fault"?"Fel":"Önskemål"}</span></div><p className="muted">{t.room || "Okänd plats"} · {t.report_count} rapport(er)</p><p>{t.description}</p><p className="muted">Ansvarig: {t.assigned_to || "Ingen"}</p>{t.duplicate_candidates.length>0&&<p className="warn">Möjlig dubblett finns</p>}<div className="actions">{t.status==="new"&&role==="worker"&&<button className="primary" onClick={()=>action(`/api/tickets/${t.id}/claim`)}>Ta ärendet</button>}{t.status==="in_progress"&&(role==="admin"||t.assigned_to) && <button className="primary" onClick={()=>action(`/api/tickets/${t.id}/complete`)}>Markera klart</button>}{t.status==="done"&&role==="worker"&&<button onClick={()=>action(`/api/tickets/${t.id}/reopen`)}>Återöppna</button>}</div></article>)}</section>)}</div></>}
    <footer>RoomTask · Intern arbetsyta för workers och administratörer</footer>
  </main>;
}
export default App;
