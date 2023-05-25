from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_botinfo(room: MatrixRoom, event: RoomMessageText, bot):
    logging("Showing bot info...")

    body = f"""GPT Info:

Model: {bot.model}
Maximum context tokens: {bot.max_tokens}
Maximum context messages: {bot.max_messages}

Room info:

Bot user ID: {bot.matrix_client.user_id}
Current room ID: {room.room_id}
System message: {bot.get_system_message(room)}

For usage statistics, run !gptbot stats
"""

    await bot.send_message(room, body, True)
