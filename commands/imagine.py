from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_imagine(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Generating image...")

        for image in bot.image_api.generate_image(prompt):
            bot.logger.log(f"Sending image...")
            await bot.send_image(room, image)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)