from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_stats(room: MatrixRoom, event: RoomMessageText, context: dict):
    context["logger"]("Showing stats...")

    if not (database := context.get("database")):
        context["logger"]("No database connection - cannot show stats")
        context["client"].room_send(
            room.room_id, "m.room.message", {"msgtype": "m.notice",
                                             "body": "Sorry, I'm not connected to a database, so I don't have any statistics on your usage."}
        )
        return

    with database.cursor() as cursor:
        cursor.execute(
            "SELECT SUM(tokens) FROM token_usage WHERE room_id = ?", (room.room_id,))
        total_tokens = cursor.fetchone()[0] or 0

    await context["client"].room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": f"Total tokens used: {total_tokens}"}
    )