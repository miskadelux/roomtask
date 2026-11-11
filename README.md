# RoomTask – första körbara grundversionen

RoomTask är ett självhostat ärendehanteringssystem med FastAPI, MySQL, React och valfri Discord-bot.

## Funktioner i denna startversion

- Publikt formulär utan namnkrav.
- Felanmälan och önskemål.
- Bilduppladdning (JPG, PNG, WebP; max 8 MB per bild; högst fyra bilder).
- Workers/admin loggar in i intern arbetsyta.
- Worker kan bara ha ett aktivt ärende åt gången (kontrolleras genom låsning av användarraden i databasen).
- Historik för skapande, tilldelning, kommentarer, avslut och återöppning.
- Enkel automatisk dubblettidentifiering med RapidFuzz. Alla rapporter sparas; dubbletter slås inte ihop automatiskt.
- Discord slash commands `/felanmalan` och `/onskemal`.
- Skrivskyddad Discord-board med kolumnerna Nya, Pågående och Klart; boten uppdaterar ett och samma meddelande automatiskt.

## Viktiga begränsningar i v0.1

Detta är en utvecklingsgrund, inte en färdig säker produktionsinstallation.

- Notis vid färdigställande skickas via valfri Discord-webhook (`DISCORD_WEBHOOK_URL`). Om Discord är nere sparas ärendet ändå; en beständig notifieringskö/outbox är en förbättring inför produktion.
- Dubblettförslag har ett grundläggande admin-API men admin-gränssnitt för att besluta om dem behöver byggas.
- Room QR-token och rumsspecifika förifyllda QR-länkar är inte färdigkopplade i formuläret ännu.
- Rate limiting/CAPTCHA måste aktiveras i reverse proxy eller läggas till innan publik drift.
- Admins särskilda återöppningsdialog är en organisatorisk process. API tillåter bara ursprunglig worker att återöppna ett färdigt ärende.
- `create_all` används för enkel utvecklingsstart. Använd Alembic-migreringar innan skarp drift.
- Behörighets- och samtidighetstester, backup/restore och säkerhetsgranskning återstår.

## 1. Installera på Debian

```bash
sudo mkdir -p /opt/roomtask
sudo chown "$USER":"$USER" /opt/roomtask
```

Packa upp projektet i `/opt/roomtask`, gå in i katalogen och skapa miljöfil:

```bash
cp .env.example .env
```

Skapa starka hemligheter, exempelvis:

```bash
openssl rand -hex 32
```

Använd separata slumpmässiga värden för `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` och `JWT_SECRET`. Sätt ett starkt `ADMIN_PASSWORD`. Ändra även `CORS_ORIGINS` när domänen är bestämd.

Starta kärnsystemet:

```bash
docker compose up -d --build
```

Skapa minst ett rum via API eller Swagger. Swagger finns på:

`http://SERVER-IP:8000/docs`

För att nå API lokalt från värddatorn kan du tillfälligt lägga till `ports: ["8000:8000"]` under api i compose. Ta bort den igen i produktion. Alternativt kör kommandot inuti containern eller använd en tillfällig SSH-tunnel.

Exempel på att skapa ett rum via Swagger: POST `/api/admin/rooms` kräver admin-token. Första admin skapas vid API-start om `ADMIN_PASSWORD` är satt.

Starta Discord-boten när Discord-inställningarna är ifyllda:

```bash
docker compose --profile discord up -d --build
```

## 2. Frontend under utveckling

Om du vill köra Vite separat:

```bash
cd frontend
npm install
npm run dev
```

Vite behöver proxykonfiguration om API körs på annan port; i Docker används Nginx-konfigurationen i projektet.

## 3. Discord

1. Skapa en applikation i Discord Developer Portal.
2. Lägg till en bot och kopiera token.
3. Bjud in boten till servern med `applications.commands` och `bot`-scopes.
4. Ge boten rätt att skicka meddelanden i loggkanalen.
5. Skapa två textkanaler, exempelvis `#roomtask-logg` och `#roomtask-board`.
6. Fyll i `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_LOG_CHANNEL_ID` och `DISCORD_BOARD_CHANNEL_ID` i `.env`.
7. Generera en separat hemlighet med `openssl rand -hex 32` och lägg den som `DISCORD_BOARD_API_KEY`. Samma hemlighet används av API och bot via `.env`.
8. Skapa vid behov en webhook och fyll i `DISCORD_WEBHOOK_URL` för separata notiser när ärenden markeras som klara.
9. Starta profilen `discord`.

### Behörigheter för Discord-boarden

- Boten behöver `View Channel`, `Send Messages`, `Embed Links` och `Read Message History` i `#roomtask-board`.
- Medlemmar som bara ska läsa boarden får `View Channel` och `Read Message History`, men nekas `Send Messages` i kanalens behörigheter.
- Boten skapar ett board-meddelande och uppdaterar samma meddelande. Den letar efter sitt befintliga board-meddelande i kanalens senaste 50 meddelanden; ge därför boten läsbehörighet till kanalhistoriken.
- `DISCORD_BOARD_REFRESH_SECONDS` styr uppdateringsintervallet och har minst 30 sekunders intervall.

Discord-boten använder det publika rapport-API:t för att skapa rapporter. Board-data hämtas från en separat intern, skrivskyddad API-endpoint som kräver `DISCORD_BOARD_API_KEY`. Den interna worker-autentiseringen är separat.

## 4. Första admin och worker-konton

Första admin skapas automatiskt om `ADMIN_PASSWORD` är satt före första uppstarten. Om databasen redan startats utan admin, skapa admin manuellt genom ett säkert engångsskript eller via en kontrollerad administrativ bootstrap. Lägg inte in lösenord i Git.

Skapa worker via admin-endpointen `POST /api/admin/users` med en admin-token.

## 5. Viktigt före publik drift

- Använd HTTPS.
- Lägg API och MySQL på ett internt Docker-nät.
- Exponera aldrig MySQL.
- Ta bort eventuella tillfälliga API-portar.
- Lägg rate limiting och CAPTCHA/Turnstile på publika formuläret.
- Kontrollera bilduppladdning och filnamn.
- Konfigurera automatiska, krypterade backuper och testa återställning.
- Byt alla standardhemligheter.
- Inför Alembic-migreringar.
- Lägg till testsvit och Discord-notifieringskö innan skarp användning.

## API

- `POST /api/public/reports` – publikt formulär, multipart/form-data.
- `POST /api/auth/login` – inloggning.
- `GET /api/tickets` – intern lista.
- `GET /api/internal/discord/board` – intern, skrivskyddad board-feed (kräver `X-RoomTask-Board-Key`).
- `POST /api/tickets/{id}/claim` – ta uppdrag.
- `POST /api/tickets/{id}/complete` – avsluta.
- `POST /api/tickets/{id}/reopen` – ursprunglig worker återöppnar.
- `GET /api/tickets/{id}/history` – historik.
- `GET /api/admin/duplicates` – dubblettförslag.
- `POST /api/admin/rooms` – skapa rum.
- `POST /api/admin/users` – skapa användare.

API-dokumentation: `/docs`.
