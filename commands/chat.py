from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_chat(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Sending chat message...")
        event.body = prompt
        await bot.process_query(room, event, allow_classify=False)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)