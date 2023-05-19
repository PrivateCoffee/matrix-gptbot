import asyncio
import functools

from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_classify(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Classifying message...")

        try:
            loop = asyncio.get_event_loop()
        except Exception as e:
            bot.logger.log(f"Error getting event loop: {e}", "error")
            await bot.send_message(
                room, "Something went wrong. Please try again.", True)
            return

        try:
            classify_partial = functools.partial(bot.classification_api.classify_message, prompt, user=room.room_id)
            response, tokens_used = await loop.run_in_executor(None, classify_partial)
        except Exception as e:
            bot.logger.log(f"Error classifying message: {e}", "error")
            await bot.send_message(room, "Sorry, I couldn't classify the message. Please try again later.", True)
            return

        message = f"The message you provided seems to be of type: {response['type']}."

        if not prompt == response["prompt"]:
            message += f"\n\nPrompt: {response['prompt']}."

        await bot.send_message(room, message, True)

        bot.log_api_usage(event, room, f"{bot.classification_api.api_code}-{bot.classification_api.classification_api}", tokens_used)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)
