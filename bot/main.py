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
NEW_REPORTS_CHANNEL_ID = int(os.getenv("DISCORD_NEW_REPORTS_CHANNEL_ID", "0") or 0)
ACTIVE_TASKS_CHANNEL_ID = int(os.getenv("DISCORD_ACTIVE_TASKS_CHANNEL_ID", "0") or 0)
COMPLETED_TASKS_CHANNEL_ID = int(os.getenv("DISCORD_COMPLETED_TASKS_CHANNEL_ID", "0") or 0)
TASK_DISCUSSION_CHANNEL_ID = int(os.getenv("DISCORD_TASK_DISCUSSION_CHANNEL_ID", "0") or 0)
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

async def save_ticket_metadata(ticket_id: int, **metadata):
    if not BOT_API_KEY:
        raise RuntimeError("DISCORD_BOT_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=15) as http:
        response = await http.patch(
            f"{API}/api/internal/discord/tickets/{ticket_id}/metadata",
            headers={"X-RoomTask-Bot-Key": BOT_API_KEY},
            json=metadata,
        )
        response.raise_for_status()
        return response.json()

BOARD_MARKER = "roomtask-board-v1"

REPORT_SESSION_TIMEOUT = 600
report_sessions = {}


def get_report_session(user_id: int):
    session = report_sessions.get(user_id)
    if session is None:
        return None

    import time
    if time.monotonic() - session["created_at"] > REPORT_SESSION_TIMEOUT:
        report_sessions.pop(user_id, None)
        return None

    return session


def clear_report_session(user_id: int):
    report_sessions.pop(user_id, None)


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)



class ReportModal(discord.ui.Modal):
    def __init__(
        self,
        kind: str,
        language: str,
        rooms: list,
        user_id: int,
        previous_data: dict | None = None,
    ):
        self.kind = kind
        self.language = language
        self.user_id = user_id
        previous_data = previous_data or {}
        self.rooms_by_id = {
            str(room["id"]): room for room in rooms
        }

        if language == "sv":
            modal_title = "Ny felanmälan" if kind == "fault" else "Nytt önskemml"
            room_label = "Rum"
            room_placeholder = "Välj ett rum..."
            title_label = "Rubrik"
            title_placeholder = "Kort sammanfattning"
            description_label = "Beskrivning"
            description_placeholder = "Beskriv felet eller önskemålet..."
            submit_label = "Fortsätt"
        else:
            modal_title = "New fault report" if kind == "fault" else "New request"
            room_label = "Room"
            room_placeholder = "Select a room..."
            title_label = "Title"
            title_placeholder = "Short summary"
            description_label = "Description"
            description_placeholder = "Describe the fault or request..."
            submit_label = "Continue"

        super().__init__(title=modal_title)

        options = [
            discord.SelectOption(
                label=room["name"][:100],
                value=str(room["id"]),
                default=str(room["id"]) == str(previous_data.get("room_id", "")),
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
            default=previous_data.get("title", ""),
            max_length=180,
        )

        self.description = discord.ui.TextInput(
            label=description_label,
            placeholder=description_placeholder,
            default=previous_data.get("description", ""),
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
        session = get_report_session(self.user_id)

        if (
            interaction.user.id != self.user_id
            or not session
            or session.get("step") != "type"
        ):
            await interaction.response.send_message(
                "This report session has expired. Please start again.",
                ephemeral=True,
            )
            return

        session["step"] = "form"

        room_id = self.room_select.values[0]
        selected_room = self.rooms_by_id.get(room_id)

        if selected_room is None:
            await interaction.response.send_message(
                "Room not found. Please start again.",
                ephemeral=True,
            )
            return

        data = {
            "kind": self.kind,
            "room_id": room_id,
            "title": str(self.title_field),
            "description": str(self.description),
            "room_name": selected_room["name"],
        }

        session["data"] = data
        session["step"] = "review"

        if self.language == "sv":
            message = (
                "**Kontrollera ditt ärende:**\n"
                f"**Typ:** {'Felanmälan' if self.kind == 'fault' else 'önskemål'}\n"
                f"**Rum:** {data['room_name']}\n"
                f"**Rubrik:** {data['title']}\n"
                f"**Beskrivning:**\n{data['description']}"
            )
        else:
            message = (
                "**Review your report:**\n"
                f"**Type:** {'Fault report' if self.kind == 'fault' else 'Request'}\n"
                f"**Room:** {data['room_name']}\n"
                f"**Title:** {data['title']}\n"
                f"**Description:**\n{data['description']}"
            )

        await interaction.response.send_message(
            message,
            view=ReportReviewView(self.user_id, self.language),
            ephemeral=True,
        )


class ReportReviewView(discord.ui.View):
    def __init__(self, user_id: int, language: str):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.language = language

    async def interaction_check(self, interaction: discord.Interaction):
        session = get_report_session(self.user_id)

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This report session belongs to another user.",
                ephemeral=True,
            )
            return False

        if not session or session.get("step") != "review":
            await interaction.response.send_message(
                "This report session has expired or moved to another step.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="Submit report",
        style=discord.ButtonStyle.success,
    )
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_report_session(self.user_id)

        if not session or not session.get("data"):
            await interaction.response.send_message(
                "Report data could not be found. Please start again.",
                ephemeral=True,
            )
            return

        session["step"] = "submitting"
        data = session["data"]

        await interaction.response.defer(ephemeral=True)

        try:
            async with httpx.AsyncClient(timeout=15) as http:
                response = await http.post(
                    f"{API}/api/public/reports",
                    data={
                        "kind": data["kind"],
                        "room_id": data["room_id"],
                        "title": data["title"],
                        "description": data["description"],
                    },
                )
                response.raise_for_status()
                result = response.json()

            clear_report_session(self.user_id)

            if self.language == "sv":
                message = f"Tack! ärende **#{result['ticket_id']}** har registrerats."
            else:
                message = f"Thank you! Ticket **#{result['ticket_id']}** has been submitted."

            await interaction.followup.send(message, ephemeral=True)

            if NEW_REPORTS_CHANNEL_ID:
                try:
                    channel = await client.fetch_channel(NEW_REPORTS_CHANNEL_ID)

                    ticket = {
                        "id": result["ticket_id"],
                        "type": data["kind"],
                        "title": data["title"],
                        "description": data["description"],
                        "room": data["room_name"],
                        "status": "new",
                        "assigned_to": None,
                    }

                    report_message = await channel.send(
                        embed=build_ticket_embed(ticket),
                        view=build_ticket_action_view(
                            ticket["id"],
                            ticket["status"],
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )

                    await save_ticket_metadata(
                        ticket["id"],
                        discord_channel_id=str(channel.id),
                        discord_message_id=str(report_message.id),
                        discord_report_channel_id=str(channel.id),
                        discord_report_message_id=str(report_message.id),
                    )

                    await create_ticket_discussion(ticket, report_message)

                except Exception as exc:
                    print(f"New report publication failed: {exc}")

            try:
                await refresh_board()
            except Exception as exc:
                print(f"Board refresh after report failed: {exc}")

        except Exception as exc:
            print(f"Report submission failed: {exc}")
            session["step"] = "review"

            message = (
                "Kunde inte registrera ärendet. Försök igen."
                if self.language == "sv"
                else "Could not submit the report. Please try again."
            )

            await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
    )
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_report_session(self.user_id)
        session["step"] = "type"
        session.pop("data", None)

        message = (
            "Vad vill du skicka in?"
            if self.language == "sv"
            else "What would you like to submit?"
        )

        await interaction.response.edit_message(
            content=message,
            view=ReportTypeView(self.user_id, self.language),
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        clear_report_session(self.user_id)

        await interaction.response.edit_message(
            content=(
                "**RoomTask ? Report a fault or submit a request**\n"
                "Choose your language to get started.\n"
                "Välj språk för att komma igång."
            ),
            view=ReportPanelView(),
        )



async def create_ticket_discussion(ticket: dict, report_message: discord.Message):
    if not TASK_DISCUSSION_CHANNEL_ID:
        raise RuntimeError("DISCORD_TASK_DISCUSSION_CHANNEL_ID is not configured")

    channel = await client.fetch_channel(TASK_DISCUSSION_CHANNEL_ID)

    thread = await channel.create_thread(
        name=f"Report #{ticket['id']} - {ticket['title']}"[:100],
        type=discord.ChannelType.public_thread,
        auto_archive_duration=10080,
        reason=f"Discussion for RoomTask report #{ticket['id']}",
    )

    await thread.send(
        f"**Discussion for Report #{ticket['id']}**\n"
        f"**Title:** {ticket['title']}\n"
        f"**Room:** {ticket.get('room') or 'Unknown'}\n"
        f"**Description:** {ticket.get('description') or 'No description provided.'}\n"
        f"**Report card:** {report_message.jump_url}",
        allowed_mentions=discord.AllowedMentions.none(),
    )

    await save_ticket_metadata(
        ticket["id"],
        discord_thread_id=str(thread.id),
    )

    return thread

async def move_ticket_card(
    ticket: dict,
    discord_metadata: dict,
    destination_channel_id: int,
    interaction: discord.Interaction,
    thread_update: str | None = None,
    history: list | None = None,
):
    if not destination_channel_id:
        raise RuntimeError("Destination Discord channel is not configured")

    destination = await client.fetch_channel(destination_channel_id)

    new_message = await destination.send(
        embed=build_ticket_embed(ticket, history),
        view=build_ticket_action_view(ticket["id"], ticket["status"]),
        allowed_mentions=discord.AllowedMentions.none(),
    )

    try:
        await save_ticket_metadata(
            ticket["id"],
            discord_channel_id=str(destination.id),
            discord_message_id=str(new_message.id),
        )
    except Exception:
        await new_message.delete()
        raise

    old_channel_id = discord_metadata.get("channel_id")
    old_message_id = discord_metadata.get("message_id")

    if not old_channel_id or not old_message_id:
        old_channel_id = str(interaction.channel_id)
        old_message_id = str(interaction.message.id) if interaction.message else None

    if old_message_id and (
        str(old_channel_id) != str(destination.id)
        or str(old_message_id) != str(new_message.id)
    ):
        try:
            old_channel = await client.fetch_channel(int(old_channel_id))
            old_message = await old_channel.fetch_message(int(old_message_id))
            await old_message.delete()
        except discord.NotFound:
            pass
        except Exception as exc:
            print(f"Old report card could not be deleted: {exc}")

    thread_id = discord_metadata.get("thread_id")
    if thread_id and thread_update:
        try:
            thread = await client.fetch_channel(int(thread_id))
            await thread.send(
                thread_update,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(f"Discussion thread update failed: {exc}")

    return new_message

def build_ticket_embed(ticket: dict, history: list | None = None) -> discord.Embed:
    status_labels = {
        "new": "New",
        "in_progress": "In progress",
        "done": "Completed",
    }

    original_description = ticket.get("description") or "No description provided."

    description = f"**Original report**\n{original_description}"

    completed_entry = next(
        (
            item for item in (history or [])
            if item.get("action") == "completed"
        ),
        None,
    )

    if ticket.get("status") == "done" and completed_entry:
        work_description = completed_entry.get("details") or ""
        work_description = work_description.removeprefix("Work completed: ")

        description += (
            f"\n\n**Work completed**\n{work_description}"
            f"\n\n**Completed by:** {completed_entry.get('actor') or 'Unknown'}"
            f"\n**Completed at:** {completed_entry.get('created_at') or 'Unknown'}"
        )

    embed = discord.Embed(
        title=f"Report #{ticket['id']}: {ticket['title']}",
        description=description[:4096],
        color=(
            discord.Color.green()
            if ticket.get("status") == "done"
            else discord.Color.blue()
        ),
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

            ticket = result["ticket"]
            discord_metadata = result.get("discord", {})
            completion_description = str(self.completion_description).strip()

            await move_ticket_card(
                ticket=ticket,
                discord_metadata=discord_metadata,
                destination_channel_id=COMPLETED_TASKS_CHANNEL_ID,
                interaction=interaction,
                thread_update=(
                    f"**Report #{self.ticket_id} completed** by "
                    f"{interaction.user.mention}.\\n"
                    f"**Work description:** {completion_description}"
                    ),
                history=result.get("history", []),
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


class ReopenTicketModal(discord.ui.Modal):
    def __init__(self, ticket_id: int):
        super().__init__(title="Reopen report")

        self.ticket_id = ticket_id

        self.reason = discord.ui.TextInput(
            label="Reason for reopening",
            placeholder="Explain why this report needs to be reopened...",
            style=discord.TextStyle.paragraph,
            min_length=1,
            max_length=1000,
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        reason = str(self.reason).strip()

        if not reason:
            await interaction.response.send_message(
                "A reason for reopening is required.",
                ephemeral=True,
            )
            return

        if self.action == "reopen":
            await interaction.response.send_modal(
                ReopenTicketModal(self.ticket_id)
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            await internal_request(
                "POST",
                f"/api/internal/discord/tickets/{self.ticket_id}/reopen",
                interaction,
                json={"reason": reason},
            )

            result = await internal_request(
                "GET",
                f"/api/internal/discord/tickets/{self.ticket_id}",
                interaction,
            )

            await move_ticket_card(
                ticket=result["ticket"],
                discord_metadata=result.get("discord", {}),
                destination_channel_id=ACTIVE_TASKS_CHANNEL_ID,
                interaction=interaction,
                thread_update=(
                    f"**Report #{self.ticket_id} reopened** by "
                    f"{interaction.user.mention}.\\n"
                    f"**Reason:** {reason}"
                ),
                history=result.get("history", []),
            )

            await interaction.followup.send(
                "Report successfully reopened.",
                ephemeral=True,
            )

        except Exception as exc:
            print(f"Ticket reopening failed: {exc}")
            await interaction.followup.send(
                f"Could not reopen report: {exc}",
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
            discord_metadata = result.get("discord", {})

            await move_ticket_card(
                ticket=ticket,
                discord_metadata=discord_metadata,
                destination_channel_id=ACTIVE_TASKS_CHANNEL_ID,
                interaction=interaction,
                thread_update=(
                    f"**Report #{self.ticket_id} claimed** by "
                    f"{interaction.user.mention}."
                    if self.action == "claim"
                    else f"**Report #{self.ticket_id} reopened** by "
                    f"{interaction.user.mention}."
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


class ReportLanguageView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction):
        session = get_report_session(interaction.user.id)

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This report session belongs to another user.",
                ephemeral=True,
            )
            return False

        if not session or session.get("step") != "language":
            await interaction.response.send_message(
                "This report session has expired or moved to another step.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(label="English", style=discord.ButtonStyle.primary)
    async def english(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_report_session(self.user_id)
        session["language"] = "en"
        session["step"] = "type"

        await interaction.response.edit_message(
            content="What would you like to submit?",
            view=ReportTypeView(self.user_id, "en"),
        )

    @discord.ui.button(label="Svenska", style=discord.ButtonStyle.primary)
    async def swedish(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_report_session(self.user_id)
        session["language"] = "sv"
        session["step"] = "type"

        await interaction.response.edit_message(
            content="Vad vill du skicka in?",
            view=ReportTypeView(self.user_id, "sv"),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        clear_report_session(self.user_id)

        await interaction.response.edit_message(
            content=(
                "**RoomTask ? Report a fault or submit a request**\n"
                "Choose your language to get started.\n"
                "Välj språk för att komma igång."
            ),
            view=ReportPanelView(),
        )


class ReportTypeView(discord.ui.View):
    def __init__(self, user_id: int, language: str):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.language = language

        if language == "sv":
            options = [
                ("Felanmälan", "fault", discord.ButtonStyle.danger),
                ("önskemål", "request", discord.ButtonStyle.success),
            ]
        else:
            options = [
                ("Report a fault", "fault", discord.ButtonStyle.danger),
                ("Submit a request", "request", discord.ButtonStyle.success),
            ]

        for label, kind, style in options:
            button = discord.ui.Button(label=label, style=style)

            async def callback(interaction: discord.Interaction, report_kind=kind):
                try:
                    session = get_report_session(self.user_id)

                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message(
                            "This report session belongs to another user.",
                            ephemeral=True,
                        )
                        return

                    if not session or session.get("step") != "type":
                        await interaction.response.send_message(
                            "This report session has expired or moved to another step.",
                            ephemeral=True,
                        )
                        return

                    session["kind"] = report_kind

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
                        ReportModal(report_kind, self.language, rooms, self.user_id)
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

    async def interaction_check(self, interaction: discord.Interaction):
        session = get_report_session(interaction.user.id)

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This report session belongs to another user.",
                ephemeral=True,
            )
            return False

        if not session or session.get("step") != "type":
            await interaction.response.send_message(
                "This report session has expired or moved to another step.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_report_session(self.user_id)
        session["step"] = "language"

        await interaction.response.edit_message(
            content="Choose your language / Välj språk:",
            view=ReportLanguageView(self.user_id),
        )


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
        import time

        user_id = interaction.user.id
        session = get_report_session(user_id)

        if session:
            await interaction.response.send_message(
                "You already have an active report session. Continue using its existing message or cancel it first.",
                ephemeral=True,
            )
            return

        report_sessions[user_id] = {
            "created_at": time.monotonic(),
            "step": "language",
        }

        await interaction.response.send_message(
            "Choose your language / Välj språk:",
            view=ReportLanguageView(user_id),
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
    import time

    user_id = interaction.user.id
    session = get_report_session(user_id)

    if session:
        await interaction.response.send_message(
            "You already have an active report session. Continue using its existing message or cancel it first.",
            ephemeral=True,
        )
        return

    report_sessions[user_id] = {
        "created_at": time.monotonic(),
        "step": "language",
    }

    await interaction.response.send_message(
        "Choose your language / Välj språk:",
        view=ReportLanguageView(user_id),
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
