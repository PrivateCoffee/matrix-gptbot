from nio import RoomMessage

async def encrypted_message_callback(room, event, bot):
    try:
        # Request room key from server
        room_key = await bot.matrix_client.request_room_key(room.room_id)

        # Attempt to decrypt the event
        decrypted_event = await bot.matrix_client.decrypt_event(event)

        # Check if decryption was successful and the decrypted event has a new type
        if isinstance(decrypted_event, RoomMessage):
            # Send the decrypted event back to _event_callback for further processing
            await bot._event_callback(room, decrypted_event)
        else:
            # Handle other decrypted event types or log a message
            bot.logger.log(f"Decrypted event of type {type(decrypted_event)}", "info")

    except Exception as e:
        bot.logger.log(f"Error decrypting event: {e}", "error")
        await bot.send_message(room.room_id, "Sorry, I was unable to decrypt your message. Please try again, or use an unencrypted room.", True)
