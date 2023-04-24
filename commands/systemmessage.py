from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_systemmessage(room: MatrixRoom, event: RoomMessageText, context: dict):
    system_message = " ".join(event.body.split()[2:])

    if system_message:
        context["logger"]("Adding system message...")

        with context["database"].cursor() as cur:
            cur.execute(
                "INSERT INTO system_messages (room_id, message_id, user_id, body, timestamp) VALUES (?, ?, ?, ?, ?)",
                (room.room_id, event.event_id, event.sender,
                 system_message, event.server_timestamp)
            )

        return room.room_id, "m.room.message", {"msgtype": "m.notice", "body": f"System message stored: {system_message}"}

    context["logger"]("Retrieving system message...")

    with context["database"].cursor() as cur:
        cur.execute(
            "SELECT body FROM system_messages WHERE room_id = ? ORDER BY timestamp DESC LIMIT 1",
            (room.room_id,)
        )
        system_message = cur.fetchone()

    if system_message is None:
        system_message = context.get("system_message", "No system message set")
    elif context.get("force_system_message") and context.get("system_message"):
        system_message = system_message + "\n\n" + context["system_message"]

    return room.room_id, "m.room.message", {"msgtype": "m.notice", "body": f"System message: {system_message}"}
