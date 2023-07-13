from mautrix.types import MessageEvent

from datetime import datetime

async def message_callback(event: MessageEvent, bot):
    bot.logger.log(f"Received message from {event.sender} in room {event.room_id}")

    sent = datetime.fromtimestamp(event.server_timestamp / 1000)
    received = datetime.now()
    latency = received - sent

    if isinstance(event, MegolmEvent):
        try:
            event = await bot.matrix_client.decrypt_event(event)
        except Exception as e:
            try:
                bot.logger.log("Requesting new encryption keys...")
                response = await bot.matrix_client.request_room_key(event)

                if isinstance(response, RoomKeyRequestError):
                    bot.logger.log(f"Error requesting encryption keys: {response}", "error")
                elif isinstance(response, RoomKeyRequestResponse):
                    bot.logger.log(f"Encryption keys received: {response}", "debug")
                    bot.matrix_bot.olm.handle_response(response)
                    event = await bot.matrix_client.decrypt_event(event)
            except:
                pass

            bot.logger.log(f"Error decrypting message: {e}", "error")
            await bot.send_message(room, "Sorry, I couldn't decrypt that message. Please try again later or switch to a room without encryption.", True)
            return

    if event.sender == bot.matrix_client.user_id:
        bot.logger.log("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot"):
        await bot.process_command(event)

    elif event.body.startswith("!"):
        bot.logger.log(f"Received {event.body} - might be a command, but not for this bot - ignoring")

    else:
        await bot.process_query(event)

    processed = datetime.now()
    processing_time = processed - received

    bot.logger.log(f"Message processing took {processing_time.total_seconds()} seconds (latency: {latency.total_seconds()} seconds)")

    if bot.room_uses_timing(event.room_id):
        await bot.send_message(event.room_id, f"Message processing took {processing_time.total_seconds()} seconds (latency: {latency.total_seconds()} seconds)", True)