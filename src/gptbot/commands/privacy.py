from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_privacy(room: MatrixRoom, event: RoomMessageText, bot):
    body = "**Privacy**\n\nIf you use this bot, note that your messages will be sent to the following recipients:\n\n"

    body += "- The bot's operator" + (f"({bot.operator})" if bot.operator else "") + "\n"

    if bot.chat_api:
        body += "- For chat requests: " + f"{bot.chat_api.operator}" + "\n"
    if bot.image_api:
        body += "- For image generation requests (!gptbot imagine): " + f"{bot.image_api.operator}" + "\n"
    if bot.calculate_api:
        body += "- For calculation requests (!gptbot calculate): " + f"{bot.calculate_api.operator}" + "\n"

    await bot.send_message(room, body, True)