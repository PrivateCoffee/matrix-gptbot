async def join_callback(response, bot):
    bot.logger.log(
        f"Join response received for room {response.room_id}", "debug")
    
    bot.matrix_client.joined_rooms()

    await bot.send_message(bot.matrix_client.rooms[response.room_id], "Hello! Thanks for inviting me! How can I help you today?")