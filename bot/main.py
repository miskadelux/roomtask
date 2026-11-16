import os
import discord
from discord import app_commands
from discord.ext import tasks
import httpx

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID", "0") or 0)
BOARD_CHANNEL_ID = int(os.getenv("DISCORD_BOARD_CHANNEL_ID", "0") or 0)
REPORT_CHANNEL_ID = int(os.getenv("DISCORD_REPORT_CHANNEL_ID", "0") or 0)
BOARD_API_KEY = os.getenv("DISCORD_BOARD_API_KEY", "")
BOT_API_KEY = os.getenv("DISCORD_BOT_API_KEY", "")
BOARD_REFRESH_SECONDS = max(30, int(os.getenv("DISCORD_BOARD_REFRESH_SECONDS", "60")))
API = os.getenv("API_BASE_URL", "http://api:8000")

def internal_headers(interaction: discord.Interaction):
    return {
        "X-RoomTask-Bot-Key": BOT_API_KEY,
        "X-Discord-User-ID": str(interaction.user.id),
    }


async def internal_request(method: str, path: str, interaction: discord.Interaction, **kwargs):
    if not BOT_API_KEY:
        raise RuntimeError("DISCORD_BOT_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=15) as http:
        response = await http.request(
            method,
            f"{API}{path}",
            headers=internal_headers(interaction),
            **kwargs,
        )

    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(str(detail))

    return response.json() if response.content else {}
BOARD_MARKER = "roomtask-board-v1"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)



class ReportModal(discord.ui.Modal):
    def __init__(self, kind: str, language: str, rooms: list):
        self.kind = kind
        self.language = language
        self.rooms_by_id = {
            str(room["id"]): room for room in rooms
        }

        if language == "sv":
            modal_title = "Ny felanmälan" if kind == "fault" else "Nytt önskemål"
            room_label = "Rum"
            room_placeholder = "Välj ett rum..."
            title_label = "Rubrik"
            title_placeholder = "Kort sammanfattning"
            description_label = "Beskrivning"
            description_placeholder = "Beskriv felet eller önskemålet..."
        else:
            modal_title = "New fault report" if kind == "fault" else "New request"
            room_label = "Room"
            room_placeholder = "Select a room..."
            title_label = "Title"
            title_placeholder = "Short summary"
            description_label = "Description"
            description_placeholder = "Describe the fault or request..."

        super().__init__(title=modal_title)

        options = [
            discord.SelectOption(
                label=room["name"][:100],
                value=str(room["id"]),
            )
            for room in rooms[:25]
        ]

        self.room_select = discord.ui.Select(
            placeholder=room_placeholder,
            min_values=1,
            max_values=1,
            options=options,
        )

        self.title_field = discord.ui.TextInput(
            label=title_label,
            placeholder=title_placeholder,
            max_length=180,
        )

        self.description = discord.ui.TextInput(
            label=description_label,
            placeholder=description_placeholder,
            style=discord.TextStyle.paragraph,
            max_length=3000,
        )

        self.add_item(
            discord.ui.Label(
                text=room_label,
                component=self.room_select,
            )
        )
        self.add_item(self.title_field)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            room_id = self.room_select.values[0]
            selected_room = self.rooms_by_id.get(room_id)

            if selected_room is None:
                await interaction.response.send_message(
                    "Room not found. Please try again.",
                    ephemeral=True,
                )
                return

            data = {
                "kind": self.kind,
                "room_id": room_id,
                "title": str(self.title_field),
                "description": str(self.description),
            }

            async with httpx.AsyncClient(timeout=15) as http:
                response = await http.post(
                    f"{API}/api/public/reports",
                    data=data,
                )
                response.raise_for_status()
                result = response.json()

            if self.language == "sv":
                message = f"Tack! Ärende **#{result['ticket_id']}** har registrerats."
            else:
                message = f"Thank you! Ticket **#{result['ticket_id']}** has been submitted."

            await interaction.response.send_message(message, ephemeral=True)

            if LOG_CHANNEL_ID:
                channel = client.get_channel(LOG_CHANNEL_ID)

                if channel:
                    ticket = {
                        "id": result["ticket_id"],
                        "type": self.kind,
                        "title": str(self.title_field),
                        "description": str(self.description),
                        "room": selected_room["name"],
                        "status": "new",
                        "assigned_to": None,
                    }

                    await channel.send(
                        embed=build_ticket_embed(ticket),
                        view=build_ticket_action_view(
                            ticket["id"],
                            ticket["status"],
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )

            await refresh_board()

        except Exception as exc:
            print(f"Report submission failed: {exc}")
            message = (
                "Kunde inte registrera ärendet. Försök igen senare."
                if self.language == "sv"
                else "Could not submit the report. Please try again later."
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)


def build_ticket_embed(ticket: dict) -> discord.Embed:
    status_labels = {
        "new": "New",
        "in_progress": "In progress",
        "done": "Completed",
    }

    embed = discord.Embed(
        title=f"Report #{ticket['id']}: {ticket['title']}",
        description=ticket.get("description") or "No description provided.",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="Type",
        value=ticket.get("type", "Unknown"),
        inline=True,
    )
    embed.add_field(
        name="Room",
        value=ticket.get("room") or "Unknown",
        inline=True,
    )
    embed.add_field(
        name="Status",
        value=status_labels.get(ticket.get("status"), ticket.get("status")),
        inline=True,
    )
    embed.add_field(
        name="Assigned to",
        value=ticket.get("assigned_to") or "Unassigned",
        inline=False,
    )

    return embed


def build_ticket_action_view(ticket_id: int, status: str):
    view = discord.ui.View(timeout=None)

    if status == "new":
        view.add_item(TicketActionButton("claim", ticket_id))

    elif status == "in_progress":
        view.add_item(TicketActionButton("complete", ticket_id))

    elif status == "done":
        view.add_item(TicketActionButton("reopen", ticket_id))

    return view


class CompleteTicketModal(discord.ui.Modal):
    def __init__(self, ticket_id: int, channel_id: int, message_id: int):
        super().__init__(title="Complete report")

        self.ticket_id = ticket_id
        self.channel_id = channel_id
        self.message_id = message_id

        self.completion_description = discord.ui.TextInput(
            label="Completion description",
            placeholder="Describe what was done...",
            style=discord.TextStyle.paragraph,
            min_length=1,
            max_length=1500,
        )

        self.add_item(self.completion_description)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            await internal_request(
                "POST",
                f"/api/internal/discord/tickets/{self.ticket_id}/complete",
                interaction,
                json={
                    "completion_description": str(self.completion_description).strip()
                },
            )

            result = await internal_request(
                "GET",
                f"/api/internal/discord/tickets/{self.ticket_id}",
                interaction,
            )

            channel = client.get_channel(self.channel_id)
            if channel is None:
                channel = await client.fetch_channel(self.channel_id)

            message = await channel.fetch_message(self.message_id)

            ticket = result["ticket"]

            await message.edit(
                embed=build_ticket_embed(ticket),
                view=build_ticket_action_view(
                    self.ticket_id,
                    ticket["status"],
                ),
            )

            await interaction.followup.send(
                "Report marked as completed.",
                ephemeral=True,
            )

        except Exception as exc:
            print(f"Ticket completion failed: {exc}")
            await interaction.followup.send(
                f"Could not complete report: {exc}",
                ephemeral=True,
            )


class TicketActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"roomtask:ticket:(?P<action>claim|complete|reopen):(?P<ticket_id>[0-9]+)",
):
    def __init__(self, action: str, ticket_id: int):
        self.action = action
        self.ticket_id = ticket_id

        labels = {
            "claim": "Claim",
            "complete": "Mark as done",
            "reopen": "Reopen",
        }

        styles = {
            "claim": discord.ButtonStyle.primary,
            "complete": discord.ButtonStyle.success,
            "reopen": discord.ButtonStyle.secondary,
        }

        super().__init__(
            discord.ui.Button(
                label=labels[action],
                style=styles[action],
                custom_id=f"roomtask:ticket:{action}:{ticket_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(
            match["action"],
            int(match["ticket_id"]),
        )

    async def callback(self, interaction: discord.Interaction):
        if self.action == "complete":
            if interaction.message is None:
                await interaction.response.send_message(
                    "Could not identify the report message.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_modal(
                CompleteTicketModal(
                    self.ticket_id,
                    interaction.channel_id,
                    interaction.message.id,
                )
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            if self.action == "claim":
                path = f"/api/internal/discord/tickets/{self.ticket_id}/claim"
                success_message = "Report successfully claimed."

            else:
                path = f"/api/internal/discord/tickets/{self.ticket_id}/reopen"
                success_message = "Report successfully reopened."

            await internal_request(
                "POST",
                path,
                interaction,
            )

            result = await internal_request(
                "GET",
                f"/api/internal/discord/tickets/{self.ticket_id}",
                interaction,
            )

            ticket = result["ticket"]

            await interaction.message.edit(
                embed=build_ticket_embed(ticket),
                view=build_ticket_action_view(
                    self.ticket_id,
                    ticket["status"],
                ),
            )

            await interaction.followup.send(
                success_message,
                ephemeral=True,
            )

        except Exception as exc:
            print(f"Ticket action failed: {exc}")
            await interaction.followup.send(
                f"Could not update report: {exc}",
                ephemeral=True,
            )


class RoomSelect(discord.ui.Select):
    def __init__(self, rooms: list, kind: str, language: str):
        self.kind = kind
        self.language = language

        options = [
            discord.SelectOption(
                label=room["name"][:100],
                value=str(room["id"]),
            )
            for room in rooms[:25]
        ]

        placeholder = (
            "Välj rum / plats..."
            if language == "sv"
            else "Select room / location..."
        )

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        room_id = int(self.values[0])
        selected_room = next(
            (room for room in self.view.rooms if int(room["id"]) == room_id),
            None,
        )

        if selected_room is None:
            await interaction.response.send_message(
                "Room not found. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            ReportModal(
                self.kind,
                self.language,
                room_id,
                selected_room["name"],
            )
        )


class RoomSelectView(discord.ui.View):
    def __init__(self, rooms: list, kind: str, language: str):
        super().__init__(timeout=180)
        self.rooms = rooms
        self.add_item(RoomSelect(rooms, kind, language))

class ReportLanguageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🇬🇧 English",
        style=discord.ButtonStyle.primary,
        custom_id="roomtask:report:english",
    )
    async def english(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "What would you like to submit?",
            view=ReportTypeView("en"),
            ephemeral=True,
        )

    @discord.ui.button(
        label="🇸🇪 Svenska",
        style=discord.ButtonStyle.primary,
        custom_id="roomtask:report:swedish",
    )
    async def swedish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Vad vill du skicka in?",
            view=ReportTypeView("sv"),
            ephemeral=True,
        )


class ReportTypeView(discord.ui.View):
    def __init__(self, language: str):
        super().__init__(timeout=180)
        self.language = language

        if language == "sv":
            options = [
                (" Felanmälan", "fault", discord.ButtonStyle.danger),
                (" Önskemål", "request", discord.ButtonStyle.success),
            ]
        else:
            options = [
                (" Report a fault", "fault", discord.ButtonStyle.danger),
                (" Submit a request", "request", discord.ButtonStyle.success),
            ]

        for label, kind, style in options:
            button = discord.ui.Button(label=label, style=style)

            async def callback(interaction: discord.Interaction, report_kind=kind):
                try:
                    async with httpx.AsyncClient(timeout=15) as http:
                        response = await http.get(f"{API}/api/rooms")
                        response.raise_for_status()
                        rooms = response.json()

                    if not rooms:
                        message = (
                            "Det finns inga rum registrerade."
                            if self.language == "sv"
                            else "There are no registered rooms."
                        )
                        await interaction.response.send_message(
                            message,
                            ephemeral=True,
                        )
                        return

                    await interaction.response.send_modal(
                        ReportModal(report_kind, self.language, rooms)
                    )

                except Exception as exc:
                    print(f"Room selection failed: {exc}")
                    message = (
                        "Kunde inte hämta rummen. Försök igen senare."
                        if self.language == "sv"
                        else "Could not load rooms. Please try again later."
                    )
                    await interaction.response.send_message(
                        message,
                        ephemeral=True,
                    )

            button.callback = callback
            self.add_item(button)



class ReportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Submit a report / Skicka in ett ärende",
        style=discord.ButtonStyle.primary,
        custom_id="roomtask:report:open",
    )
    async def open_report(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_message(
            "Choose your language / Välj språk:",
            view=ReportLanguageView(),
            ephemeral=True,
        )

REPORT_PANEL_MARKER = "roomtask-report-panel"


async def ensure_report_panel():
    if not REPORT_CHANNEL_ID:
        print("DISCORD_REPORT_CHANNEL_ID is not configured")
        return

    try:
        channel = client.get_channel(REPORT_CHANNEL_ID)

        if channel is None:
            channel = await client.fetch_channel(REPORT_CHANNEL_ID)

        async for message in channel.history(limit=50):
            if (
                message.author == client.user
                and REPORT_PANEL_MARKER in message.content
            ):
                await message.edit(
                    content=(
                        "**RoomTask – Report a fault or submit a request**\n"
                        "Choose your language to get started.\n"
                        "Välj språk för att komma igång.\n\n"
                        f"{REPORT_PANEL_MARKER}"
                    ),
                    view=ReportPanelView(),
                )
                print("RoomTask report panel updated")
                return

        await channel.send(
            content=(
                "**RoomTask – Report a fault or submit a request**\n"
                "Choose your language to get started.\n"
                "Välj språk för att komma igång.\n\n"
                f"{REPORT_PANEL_MARKER}"
            ),
            view=ReportPanelView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        print("RoomTask report panel created")

    except Exception as exc:
        print(f"RoomTask report panel setup failed: {exc}")

@tree.command(name="ticket", description="View details of a ticket")
@app_commands.describe(ticket_id="The ticket ID")
async def ticket(interaction: discord.Interaction, ticket_id: int):
    await interaction.response.defer(ephemeral=True)

    try:
        result = await internal_request(
            "GET",
            f"/api/internal/discord/tickets/{ticket_id}",
            interaction,
        )

        t = result["ticket"]
        embed = discord.Embed(
            title=f"Ticket #{t['id']} – {t['title']}",
            description=t["description"][:4000],
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Type", value=t["type"], inline=True)
        embed.add_field(name="Status", value=t["status"], inline=True)
        embed.add_field(name="Room", value=t["room"] or "Unknown", inline=True)
        embed.add_field(name="Assigned to", value=t["assigned_to"] or "Unassigned", inline=True)
        embed.add_field(name="Reports", value=str(t["report_count"]), inline=True)
        embed.add_field(name="Created", value=t["created_at"][:10], inline=True)

        if t["completed_at"]:
            embed.add_field(name="Completed", value=t["completed_at"][:10], inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as exc:
        await interaction.followup.send(f"Could not retrieve ticket: {exc}", ephemeral=True)

@tree.command(name="claim", description="Claim an unassigned ticket")
@app_commands.describe(ticket_id="The ticket ID to claim")
async def claim(interaction: discord.Interaction, ticket_id: int):
    await interaction.response.defer(ephemeral=True)

    try:
        result = await internal_request(
            "POST",
            f"/api/internal/discord/tickets/{ticket_id}/claim",
            interaction,
        )
        await interaction.followup.send(
            f"Ticket **#{ticket_id}** has been assigned to you.",
            ephemeral=True,
        )
        await refresh_board()

    except Exception as exc:
        await interaction.followup.send(
            f"Could not claim ticket: {exc}",
            ephemeral=True,
        )


class CommentModal(discord.ui.Modal):
    def __init__(self, ticket_id: int):
        super().__init__(title=f"Comment on ticket #{ticket_id}")
        self.ticket_id = ticket_id
        self.body = discord.ui.TextInput(
            label="Comment",
            style=discord.TextStyle.paragraph,
            placeholder="Write your comment...",
            max_length=4000,
        )
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            await internal_request(
                "POST",
                f"/api/internal/discord/tickets/{self.ticket_id}/comments",
                interaction,
                json={"body": str(self.body)},
            )
            await interaction.followup.send(
                f"Comment added to ticket **#{self.ticket_id}**.",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                f"Could not add comment: {exc}",
                ephemeral=True,
            )


@tree.command(name="comment", description="Add a comment to a ticket")
@app_commands.describe(ticket_id="The ticket ID")
async def comment(interaction: discord.Interaction, ticket_id: int):
    await interaction.response.send_modal(CommentModal(ticket_id))

@tree.command(name="report", description="Submit a fault report or request")
async def report(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Choose your language / Välj språk:",
        view=ReportLanguageView(),
        ephemeral=True,
    )


def build_board_embed(payload: dict) -> discord.Embed:
    columns = payload.get("columns", {})
    embed = discord.Embed(
        title="RoomTask – Ärendeöversikt",
        description="Automatiskt uppdaterad från RoomTask. Ärenden hanteras i RoomTask, inte i Discord.",
        color=discord.Color.blurple(),
    )
    definitions = [
        ("new", "Nya"),
        ("in_progress", " Pågående"),
        ("done", "Klart"),
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
            line = f"**#{ticket['id']}** {title}\n {room}"
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

    if not getattr(client, "report_view_registered", False):
        client.add_view(ReportPanelView())
        client.report_view_registered = True

    if not getattr(client, "ticket_action_items_registered", False):
        client.add_dynamic_items(TicketActionButton)
        client.ticket_action_items_registered = True

    await ensure_report_panel()

    if BOARD_CHANNEL_ID and BOARD_API_KEY and not board_refresh_loop.is_running():
        board_refresh_loop.start()

    print(f"RoomTask bot online as {client.user}")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN saknas")
client.run(TOKEN)
