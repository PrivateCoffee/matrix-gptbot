from nio import MatrixRoom, RoomMessageText, MegolmEvent

async def message_callback(room: MatrixRoom, event: RoomMessageText | MegolmEvent, bot):
    bot.logger.log(f"Received message from {event.sender} in room {room.room_id}")

    if isinstance(event, MegolmEvent):
        try:
            event = await bot.matrix_client.decrypt_event(event)
        except Exception as e:
            try:
                bot.logger.log("Requesting new encryption keys...")
                await bot.matrix_client.request_room_key(event)
            except:
                pass

            bot.logger.log(f"Error decrypting message: {e}", "error")
            await bot.send_message(room, "Sorry, I couldn't decrypt that message. Please try again later or switch to a room without encryption.", True)
            return

    if event.sender == bot.matrix_client.user_id:
        bot.logger.log("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot"):
        await bot.process_command(room, event)

    elif event.body.startswith("!"):
        bot.logger.log(f"Received {event.body} - might be a command, but not for this bot - ignoring")

    else:
        await bot.process_query(room, event)