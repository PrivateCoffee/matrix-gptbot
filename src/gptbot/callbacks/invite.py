from nio import InviteEvent, MatrixRoom

async def room_invite_callback(room: MatrixRoom, event: InviteEvent, bot):
    if room.room_id in bot.matrix_client.rooms:
        bot.logger.log(f"Already in room {room.room_id} - ignoring invite")
        return

    bot.logger.log(f"Received invite to room {room.room_id} - joining...")

    await bot.matrix_client.join(room.room_id)