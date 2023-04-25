from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_help(room: MatrixRoom, event: RoomMessageText, bot):
    body = """Available commands:

!gptbot help - Show this message
!gptbot newroom <room name> - Create a new room and invite yourself to it
!gptbot stats - Show usage statistics for this room
!gptbot botinfo - Show information about the bot
!gptbot coin - Flip a coin (heads or tails)
!gptbot ignoreolder - Ignore messages before this point as context
!gptbot systemmessage - Get or set the system message for this room
"""

    await bot.send_message(room, body, True)