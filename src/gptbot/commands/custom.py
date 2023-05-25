from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_custom(room: MatrixRoom, event: RoomMessageText, bot):
    bot.logger.log("Forwarding custom command to room...")
    await bot.process_query(room, event)

    return