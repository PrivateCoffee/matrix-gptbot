from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_unknown(room: MatrixRoom, event: RoomMessageText, context: dict):
    bot.logger.log("Unknown command")

    bot.send_message(room, "Unknown command - try !gptbot help", True)