from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_unknown(room: MatrixRoom, event: RoomMessageText, context: dict):
    context["logger"]("Unknown command")

    return room.room_id, "m.room.message", {"msgtype": "m.notice",
                                            "body": "Unknown command - try !gptbot help"}
