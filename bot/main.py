import os
import discord
from discord import app_commands
from discord.ext import tasks
import httpx

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID", "0") or 0)
BOARD_CHANNEL_ID = int(os.getenv("DISCORD_BOARD_CHANNEL_ID", "0") or 0)
BOARD_API_KEY = os.getenv("DISCORD_BOARD_API_KEY", "")
BOARD_REFRESH_SECONDS = max(30, int(os.getenv("DISCORD_BOARD_REFRESH_SECONDS", "60")))
API = os.getenv("API_BASE_URL", "http://api:8000")
BOARD_MARKER = "roomtask-board-v1"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


class ReportModal(discord.ui.Modal):
    def __init__(self, kind: str):
        super().__init__(title="Ny felanmälan" if kind == "fault" else "Nytt önskemål")
        self.kind = kind
        self.room = discord.ui.TextInput(label="Rum/plats", placeholder="Exempel: Rum 203", max_length=120)
        self.title_field = discord.ui.TextInput(label="Rubrik", placeholder="Kort sammanfattning", max_length=180)
        self.description = discord.ui.TextInput(label="Beskrivning", style=discord.TextStyle.paragraph, max_length=3000)
        self.add_item(self.room)
        self.add_item(self.title_field)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        async with httpx.AsyncClient(timeout=15) as http:
            rooms_response = await http.get(f"{API}/api/rooms")
            rooms_response.raise_for_status()
            rooms = rooms_response.json()
            match = next((r for r in rooms if r["name"].lower() == str(self.room).strip().lower()), None)
            if not match:
                await interaction.response.send_message("Jag hittar inte det rummet. Kontrollera rumsnamnet.", ephemeral=True)
                return
            data = {"kind": self.kind, "room_id": str(match["id"]), "title": str(self.title_field), "description": str(self.description)}
            response = await http.post(f"{API}/api/public/reports", data=data)
            if response.status_code >= 400:
                await interaction.response.send_message("Kunde inte registrera ärendet. Försök igen senare.", ephemeral=True)
                return
            result = response.json()
        await interaction.response.send_message(f"Tack! Ärende **#{result['ticket_id']}** har registrerats.", ephemeral=True)
        if LOG_CHANNEL_ID:
            channel = client.get_channel(LOG_CHANNEL_ID)
            if channel:
                await channel.send(
                    f"📥 Nytt ärende **#{result['ticket_id']}** · "
                    f"{'Felanmälan' if self.kind == 'fault' else 'Önskemål'} · {self.room.value}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        await refresh_board()


@tree.command(name="felanmalan", description="Skicka in en felanmälan")
async def fault(interaction: discord.Interaction):
    await interaction.response.send_modal(ReportModal("fault"))


@tree.command(name="onskemal", description="Skicka in ett önskemål")
async def request(interaction: discord.Interaction):
    await interaction.response.send_modal(ReportModal("request"))


def build_board_embed(payload: dict) -> discord.Embed:
    columns = payload.get("columns", {})
    embed = discord.Embed(
        title="RoomTask – Ärendeöversikt",
        description="Automatiskt uppdaterad från RoomTask. Ärenden hanteras i RoomTask, inte i Discord.",
        color=discord.Color.blurple(),
    )
    definitions = [
        ("new", "🆕 Nya"),
        ("in_progress", "🔧 Pågående"),
        ("done", "✅ Klart"),
    ]
    for key, label in definitions:
        column = columns.get(key, {})
        tickets = column.get("tickets", [])
        total = int(column.get("total", len(tickets)))
        lines = []
        for ticket in tickets[:12]:
            title = str(ticket.get("title", "Utan rubrik")).replace("\n", " ").strip()
            if len(title) > 75:
                title = title[:72] + "…"
            room = str(ticket.get("room") or "Okänd plats")
            assignee = ticket.get("assigned_to")
            line = f"**#{ticket['id']}** {title}\n📍 {room}"
            if assignee:
                line += f" · 👤 {assignee}"
            lines.append(line)
        if not lines:
            value = "*Inga ärenden*"
        else:
            value = "\n\n".join(lines)
        if total > len(tickets):
            value += f"\n\n… och {total - len(tickets)} till"
        embed.add_field(name=f"{label} · {total}", value=value[:1024], inline=True)
    embed.set_footer(text=f"{BOARD_MARKER} · Uppdateras automatiskt var {BOARD_REFRESH_SECONDS} sekund")
    return embed


async def refresh_board():
    if not BOARD_CHANNEL_ID or not BOARD_API_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.get(
                f"{API}/api/internal/discord/board",
                headers={"X-RoomTask-Board-Key": BOARD_API_KEY},
            )
            response.raise_for_status()
            payload = response.json()
        channel = client.get_channel(BOARD_CHANNEL_ID)
        if channel is None:
            channel = await client.fetch_channel(BOARD_CHANNEL_ID)
        embed = build_board_embed(payload)
        marker = BOARD_MARKER
        async for message in channel.history(limit=50):
            if message.author.id == client.user.id and message.embeds:
                footer = message.embeds[0].footer.text or ""
                if marker in footer:
                    await message.edit(embed=embed, content=None, allowed_mentions=discord.AllowedMentions.none())
                    return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"RoomTask Discord board update failed: {exc}")


@tasks.loop(seconds=BOARD_REFRESH_SECONDS)
async def board_refresh_loop():
    await refresh_board()


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    if BOARD_CHANNEL_ID and BOARD_API_KEY and not board_refresh_loop.is_running():
        board_refresh_loop.start()
    print(f"RoomTask bot online as {client.user}")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN saknas")
client.run(TOKEN)
