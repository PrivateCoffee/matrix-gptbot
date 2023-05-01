from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_help(room: MatrixRoom, event: RoomMessageText, bot):
    body = """Available commands:

- !gptbot help - Show this message
- !gptbot botinfo - Show information about the bot
- !gptbot privacy - Show privacy information
- !gptbot newroom \<room name\> - Create a new room and invite yourself to it
- !gptbot stats - Show usage statistics for this room
- !gptbot systemmessage \<message\> - Get or set the system message for this room
- !gptbot coin - Flip a coin (heads or tails)
- !gptbot imagine \<prompt\> - Generate an image from a prompt
- !gptbot calculate [--text] [--details] \<query\> - Calculate a result to a calculation, optionally forcing text output instead of an image, and optionally showing additional details like the input interpretation
- !gptbot chat \<message\> - Send a message to the chat API
- !gptbot classify \<message\> - Classify a message using the classification API
- !gptbot custom \<message\> - Used for custom commands handled by the chat model and defined through the room's system message
- !gptbot ignoreolder - Ignore messages before this point as context
"""

    await bot.send_message(room, body, True)
