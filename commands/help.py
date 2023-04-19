from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_help(room: MatrixRoom, event: RoomMessageText, context: dict):
    await context["client"].room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": """Available commands:

!gptbot help - Show this message
!gptbot newroom <room name> - Create a new room and invite yourself to it
!gptbot stats - Show usage statistics for this room
!gptbot botinfo - Show information about the bot
!gptbot coin - Flip a coin (heads or tails)
!gptbot ignoreolder - Ignore messages before this point as context
"""}
    )