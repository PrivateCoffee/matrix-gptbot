from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_botinfo(room: MatrixRoom, event: RoomMessageText, context: dict):
    logging("Showing bot info...")

    await context["client"].room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": f"""GPT Info:

Model: {context["model"]}
Maximum context tokens: {context["max_tokens"]}
Maximum context messages: {context["max_messages"]}
System message: {context["system_message"]}

Room info:

Bot user ID: {context["client"].user_id}
Current room ID: {room.room_id}

For usage statistics, run !gptbot stats
"""})