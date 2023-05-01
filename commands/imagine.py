from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_imagine(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Generating image...")

        images, tokens_used = bot.image_api.generate_image(prompt, user=room.room_id)

        for image in images:
            bot.logger.log(f"Sending image...")
            await bot.send_image(room, image)

        bot.log_api_usage(event, room, f"{self.image_api.api_code}-{self.image_api.image_api}", tokens_used)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)