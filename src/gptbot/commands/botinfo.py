from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_botinfo(room: MatrixRoom, event: RoomMessageText, bot):
    bot.logger.log("Showing bot info...")

    body = f"""GPT Room info:

Model: {await bot.get_room_model(room)}\n
Maximum context tokens: {bot.chat_api.max_tokens}\n
Maximum context messages: {bot.chat_api.max_messages}\n
Bot user ID: {bot.matrix_client.user_id}\n
Current room ID: {room.room_id}\n
System message: {bot.get_system_message(room)}
"""

    await bot.send_message(room, body, True)
