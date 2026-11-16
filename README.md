# RoomTask – självhostat ärendehanteringssystem

RoomTask är ett självhostat ärendehanteringssystem för felanmälningar och önskemål i olika rum och lokaler.

Systemet består av ett publikt rapportformulär, en intern arbetsyta för workers och admins, ett REST API, en MySQL-databas och en valfri Discord-bot.

## Teknikstack

- **Backend:** Python, FastAPI, SQLAlchemy
- **Databas:** MySQL
- **Frontend:** React, TypeScript, Vite
- **Webbserver:** Nginx
- **Containerhantering:** Docker Compose
- **Discord:** Python och discord.py
- **Dubblettidentifiering:** RapidFuzz

## Funktioner

### Publik felanmälan

- Publikt formulär utan krav på användarkonto eller namn.
- Stöd för felanmälningar och önskemål.
- Bilduppladdning med JPG, PNG och WebP.
- Max 8 MB per bild och högst fyra bilder per rapport.
- Möjlighet att rapportera direkt till ett förvalt rum via en unik QR-kod.
- Rapporter sparas även om en möjlig dubblett identifieras.

### Intern arbetsyta

- Separat inloggning för workers och admins.
- Översikt över nya, pågående och avslutade ärenden.
- Möjlighet att ta över och avsluta ärenden.
- En worker kan endast ha ett aktivt ärende åt gången.
- Kommentarer på ärenden.
- Redigering och borttagning av kommentarer enligt behörighetsreglerna.
- Historik över viktiga händelser.
- Visning av rapporter och bilagor.
- Möjlighet att återöppna avslutade ärenden.

### Dubblettidentifiering

- Automatisk identifiering av möjliga dubbletter med RapidFuzz.
- Alla rapporter sparas separat.
- Dubbletter slås inte ihop automatiskt.
- Admin kan starta en ny dubblettsökning.
- Admin kan granska förslag och länka eller avvisa dem.
- Möjliga dubbletter visas även i ärendeinformationen.

### Rumsadministration och QR-koder

- Admin kan skapa och administrera rum.
- Varje rum har en unik QR-token.
- QR-koder genereras i administrationsgränssnittet.
- QR-koden öppnar rapportformuläret med rätt rum förvalt.
- Inaktiva eller ogiltiga rumstoken avvisas.

### Användaradministration

- Admin kan skapa användarkonton.
- Admin kan ändra användaruppgifter och återställa lösenord.
- Discord-konton kan länkas till RoomTask-användare.
- Discord-koppling kan ändras eller tas bort.

### Discord-integration

Discord-integrationen består av en bot och en separat intern API-kommunikation.

Boten har följande funktioner:

- Slash-kommandot `/fault` för felanmälningar.
- Slash-kommandot `/request` för önskemål.
- Automatisk, skrivskyddad ärendeboard.
- Boarden visar nya, pågående och avslutade ärenden.
- Samma board-meddelande uppdateras automatiskt i stället för att ett nytt meddelande skapas varje gång.
- Valfri webhook-notis när ett ärende avslutas.

RoomTask har även interna API-endpoints för Discord-integration:

- Hämta board-data.
- Hämta information om ett enskilt ärende.
- Låta en länkad worker ta över ett ärende.
- Låta en behörig användare avsluta ett ärende.
- Lägga till kommentarer.

**Observera:** De interna Discord-endpointsen finns i backend, men botens funktioner för att ta över ärenden, avsluta ärenden och kommentera är ännu inte färdigkopplade.

---

## Begränsningar och utvecklingsstatus

RoomTask är en utvecklingsversion och ska inte betraktas som en färdig säker produktionsinstallation.

Följande områden behöver vidareutvecklas eller verifieras innan skarp drift:

- Rate limiting och CAPTCHA/Turnstile för det publika formuläret.
- Säkerhetsgranskning av API, autentisering och filuppladdning.
- Automatiserade tester av behörigheter och samtidiga databasoperationer.
- Automatiska backuper och verifierade återställningstester.
- Alembic-migreringar i stället för enbart `create_all`.
- Beständig notifieringskö för Discord-notiser.
- Färdigkoppling av Discord-botens interna funktioner för ärendehantering.
- Testning av hela flödet från rapport till avslutat ärende.

Discord-webhooken är valfri. Om Discord inte är tillgängligt kan själva ärendet fortfarande sparas, men notifieringen kan misslyckas.

## 1. Installation på Debian

Skapa installationskatalogen:

```bash
sudo mkdir -p /opt/roomtask
sudo chown "$USER":"$USER" /opt/roomtask
```

Packa upp projektet i `/opt/roomtask` och gå till katalogen:

```bash
cd /opt/roomtask
```

Skapa miljöfilen:

```bash
cp .env.example .env
```

Generera starka hemligheter:

```bash
openssl rand -hex 32
```

Använd separata slumpmässiga värden för:

- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `JWT_SECRET`
- `DISCORD_BOARD_API_KEY`
- `DISCORD_BOT_API_KEY`

Använd ett starkt `ADMIN_PASSWORD`.

Kontrollera även att `CORS_ORIGINS` innehåller rätt domän när webbplatsens adress är bestämd.

### Starta kärnsystemet

```bash
docker compose up -d --build
```

Kontrollera containrarna:

```bash
docker compose ps
```

API-dokumentationen finns på:

```text
http://SERVER-IP:8000/docs
```

För att nå API:t från värddatorn under installation kan port 8000 tillfälligt exponeras i Docker Compose. Ta bort den exponeringen inför produktion och använd en reverse proxy.

### Skapa det första rummet

Minst ett rum behöver skapas innan systemet kan användas fullt ut.

Swagger-dokumentationen finns på `/docs`.

Admin-endpointen för att skapa rum är:

```text
POST /api/admin/rooms
```

Första admin-kontot skapas automatiskt vid API-start om `ADMIN_PASSWORD` är konfigurerat.

### Starta Discord-boten

När Discord-inställningarna är ifyllda kan boten startas separat:

```bash
docker compose --profile discord up -d --build bot
```

---

## 2. Frontend under utveckling

Frontend kan köras separat med Vite.

Gå till frontend-katalogen:

```bash
cd frontend
```

Installera beroenden:

```bash
npm install
```

Starta utvecklingsservern:

```bash
npm run dev
```

Vite behöver en korrekt proxykonfiguration om API:t körs på en annan port.

I Docker används projektets Nginx-konfiguration.

---

## 3. Discord-konfiguration

### Skapa Discord-boten

1. Öppna Discord Developer Portal.
2. Skapa en ny applikation.
3. Lägg till en bot.
4. Kopiera botens token.
5. Bjud in boten till Discord-servern med behörigheterna `bot` och `applications.commands`.
6. Ge boten tillgång till de kanaler den behöver använda.

### Miljövariabler

Fyll i följande värden i `.env`:

| Variabel | Beskrivning |
|---|---|
| `DISCORD_TOKEN` | Botens hemliga token |
| `DISCORD_GUILD_ID` | Discord-serverns ID |
| `DISCORD_LOG_CHANNEL_ID` | ID för loggkanalen |
| `DISCORD_BOARD_CHANNEL_ID` | ID för board-kanalen |
| `DISCORD_BOARD_API_KEY` | Hemlighet för boardens interna API |
| `DISCORD_BOT_API_KEY` | Hemlighet för botens interna API |
| `DISCORD_BOARD_REFRESH_SECONDS` | Intervall för board-uppdatering |
| `DISCORD_WEBHOOK_URL` | Valfri webhook för avslutsnotiser |

Använd separata slumpmässiga hemligheter för `DISCORD_BOARD_API_KEY` och `DISCORD_BOT_API_KEY`.

Generera dem exempelvis med:

```bash
openssl rand -hex 32
```

Lägg aldrig botens token eller API-hemligheter i Git.

### Discord-board

Boten skapar och uppdaterar en board med följande statuskolumner:

- New
- In Progress
- Completed

Boten försöker hitta sitt tidigare board-meddelande bland kanalens senaste 50 meddelanden och uppdaterar det.

Boten behöver följande behörigheter i board-kanalen:

- View Channel
- Send Messages
- Embed Links
- Read Message History

Medlemmar som endast ska läsa boarden behöver:

- View Channel
- Read Message History

Neka `Send Messages` för vanliga medlemmar i board-kanalen om den ska vara skrivskyddad.

### Intern Discord-autentisering

Board-endpointen använder:

```text
X-RoomTask-Board-Key
```

De övriga interna Discord-endpointsen använder:

```text
X-RoomTask-Bot-Key
X-Discord-User-ID
```

Discord-användaren måste vara kopplad till ett aktivt RoomTask-konto för att kunna använda de interna användarfunktionerna.

---

## 4. Användarroller och behörigheter

### Worker

En worker kan:

- Se ärenden.
- Ta över ett ledigt ärende.
- Ha högst ett aktivt ärende åt gången.
- Kommentera ärenden.
- Avsluta tilldelade ärenden.
- Återöppna egna tilldelade ärenden som har avslutats.

### Admin

En admin kan:

- Administrera användare.
- Skapa och administrera rum.
- Hantera Discord-kopplingar.
- Granska dubblettförslag.
- Ta över och hantera ärenden.
- Återöppna avslutade ärenden.
- Hantera övriga administrativa funktioner.

### Regler för aktiva ärenden

En worker får inte ta över ett nytt ärende om personen redan har ett aktivt ärende.

Kontrollen görs i backend och skyddas med databaslåsning för att minska risken för samtidiga tilldelningar.

---

## 5. API

API:t är uppdelat i publika, autentiserade, administrativa och interna endpoints.

### Hälsa och autentisering

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/health` | Hälsokontroll |
| POST | `/api/auth/login` | Logga in |
| GET | `/api/auth/me` | Hämta inloggad användare |

### Rum och publika rapporter

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/rooms` | Hämta tillgängliga rum |
| GET | `/api/public/rooms/{qr_token}` | Hämta rum via QR-token |
| POST | `/api/public/reports` | Skapa publik rapport |

### Ärenden

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/tickets` | Lista ärenden |
| GET | `/api/tickets/{ticket_id}` | Hämta ärende |
| GET | `/api/tickets/{ticket_id}/details` | Hämta detaljerad ärendeinformation |
| POST | `/api/tickets/{ticket_id}/claim` | Ta över ärende |
| POST | `/api/tickets/{ticket_id}/complete` | Avsluta ärende |
| POST | `/api/tickets/{ticket_id}/reopen` | Återöppna ärende |
| GET | `/api/tickets/{ticket_id}/history` | Hämta historik |
| GET | `/api/tickets/{ticket_id}/comments` | Hämta kommentarer |
| POST | `/api/tickets/{ticket_id}/comments` | Lägg till kommentar |
| PUT | `/api/tickets/{ticket_id}/comments/{comment_id}` | Redigera kommentar |
| DELETE | `/api/tickets/{ticket_id}/comments/{comment_id}` | Ta bort kommentar |
| GET | `/api/tickets/{ticket_id}/attachments/{attachment_id}` | Hämta bilaga |

### Dubbletter

| Metod | Endpoint | Beskrivning |
|---|---|---|
| POST | `/api/admin/duplicates/scan` | Starta dubblettsökning |
| GET | `/api/admin/duplicates` | Lista dubblettförslag |
| POST | `/api/admin/duplicates/{match_id}/decision` | Besluta om dubblettförslag |

### Administration

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/admin/rooms` | Lista rum |
| POST | `/api/admin/rooms` | Skapa rum |
| GET | `/api/admin/users` | Lista användare |
| POST | `/api/admin/users` | Skapa användare |
| PUT | `/api/admin/users/{user_id}` | Ändra användare |
| PUT | `/api/admin/users/{user_id}/password` | Återställ lösenord |
| PUT | `/api/admin/users/{user_id}/discord` | Koppla Discord-konto |

### Interna Discord-endpoints

| Metod | Endpoint | Beskrivning |
|---|---|---|
| GET | `/api/internal/discord/board` | Hämta board-data |
| GET | `/api/internal/discord/tickets/{ticket_id}` | Hämta ärendeinformation |
| POST | `/api/internal/discord/tickets/{ticket_id}/claim` | Ta över ärende via Discord |
| POST | `/api/internal/discord/tickets/{ticket_id}/complete` | Avsluta ärende via Discord |
| POST | `/api/internal/discord/tickets/{ticket_id}/comments` | Kommentera ärende via Discord |

De interna Discord-endpointsen kräver särskilda API-nycklar och, där det är relevant, ett länkat Discord-konto.

Fullständig API-dokumentation finns i Swagger:

```text
/docs
```

---

## 6. Viktigt före produktionsdrift

Innan systemet används i skarp drift bör följande genomföras:

- [ ] HTTPS med giltigt TLS-certifikat.
- [ ] API och databas på internt Docker-nät.
- [ ] Ingen direkt exponering av MySQL.
- [ ] Inga onödiga publika API-portar.
- [ ] Stark autentisering och säkra hemligheter.
- [ ] Rate limiting för publika endpoints.
- [ ] CAPTCHA eller motsvarande skydd mot automatiserade rapporter.
- [ ] Säkerhetsgranskning av bilduppladdning och filhantering.
- [ ] Automatiska backuper av databasen.
- [ ] Testad återställning från backup.
- [ ] Alembic-migreringar för databasschemat.
- [ ] Automatiserade tester av behörigheter och samtidighet.
- [ ] Beständig kö för Discord-notifieringar.
- [ ] Test av Discord-botens interna ärendefunktioner.
- [ ] Kontroll av loggning och hantering av känsliga uppgifter.

## Projektstatus

RoomTask har en fungerande grund med publik rapportering, intern ärendehantering, administration, QR-koder, dubblettgranskning och en grundläggande Discord-integration.

Projektet utvecklas vidare med fokus på säkerhet, stabilitet, automatisering och en mer komplett Discord-integration.