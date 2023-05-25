from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_ignoreolder(room: MatrixRoom, event: RoomMessageText, bot):
    body = """Alright, messages before this point will not be processed as context anymore.
                                         
If you ever reconsider, you can simply delete your message and I will start processing messages before it again."""

    await bot.send_message(room, body, True)