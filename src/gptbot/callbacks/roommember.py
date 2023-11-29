from nio import RoomMemberEvent, MatrixRoom, KeysUploadError

async def roommember_callback(room: MatrixRoom, event: RoomMemberEvent, bot):
    try:
        await bot.matrix_client.keys_upload()
    except KeysUploadError as e:
        bot.logger.log(f"Failed to upload keys: {e.message}")

    if event.membership == "leave":
        bot.logger.log(f"User {event.state_key} left room {room.room_id} - am I alone now?")

        if len(room.users) == 1:
            bot.logger.log("Yes, I was abandoned - leaving...")
            await bot.matrix_client.room_leave(room.room_id)
            return
