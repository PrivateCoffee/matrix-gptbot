import asyncio
import functools

from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_imagine(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Generating image...")

        try:
            loop = asyncio.get_event_loop()
        except Exception as e:
            bot.logger.log(f"Error getting event loop: {e}", "error")
            await bot.send_message(
                room, "Something went wrong. Please try again.", True)
            return

        try:
            image_partial = functools.partial(bot.image_api.generate_image, prompt, user=room.room_id)
            images, tokens_used = await loop.run_in_executor(None, image_partial)
        except Exception as e:
            bot.logger.log(f"Error generating image: {e}", "error")
            await bot.send_message(room, "Sorry, I couldn't generate an image. Please try again later.", True)
            return

        for image in images:
            bot.logger.log(f"Sending image...")
            await bot.send_image(room, image)

        bot.log_api_usage(event, room, f"{bot.image_api.api_code}-{bot.image_api.image_api}", tokens_used)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)
