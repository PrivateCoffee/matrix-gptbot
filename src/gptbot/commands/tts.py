from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_tts(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = " ".join(event.body.split()[2:])

    if prompt:
        bot.logger.log("Generating speech...")

        try:
            content = await bot.tts_api.text_to_speech(prompt, user=room.room_id)
        except Exception as e:
            bot.logger.log(f"Error generating speech: {e}", "error")
            await bot.send_message(room, "Sorry, I couldn't generate an audio file. Please try again later.", True)
            return

        bot.logger.log(f"Sending audio file...")
        await bot.send_file(room, content, "audio.mp3", "audio/mpeg", "m.audio")

        return

    await bot.send_message(room, "You need to provide a prompt.", True)
