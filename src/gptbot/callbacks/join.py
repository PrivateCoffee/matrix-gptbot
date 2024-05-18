from contextlib import closing

async def join_callback(response, bot):
    bot.logger.log(
        f"Join response received for room {response.room_id}", "debug")
    
    bot.matrix_client.joined_rooms()

    with closing(bot.database.cursor()) as cursor:
        cursor.execute(
            "SELECT space_id FROM user_spaces WHERE user_id = ? AND active = TRUE", (response.sender,))
        space = cursor.fetchone()

    if space:
        bot.logger.log(f"Adding new room to space {space[0]}...")
        await bot.add_rooms_to_space(space[0], [response.room_id])

    bot.matrix_client.keys_upload()

    await bot.send_message(bot.matrix_client.rooms[response.room_id], "Hello! Thanks for inviting me! How can I help you today?")