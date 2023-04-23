from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_ignoreolder(room: MatrixRoom, event: RoomMessageText, context: dict):
    return room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": """Alright, messages before this point will not be processed as context anymore.
                                         
If you ever reconsider, you can simply delete your message and I will start processing messages before it again."""}