from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom
from nio.responses import RoomInviteError

from contextlib import closing


async def command_space(room: MatrixRoom, event: RoomMessageText, bot):
    if len(event.body.split()) == 3:
        request = event.body.split()[2]

        if request.lower() == "enable":
            bot.logger.log("Enabling space...")

            with closing(bot.database.cursor()) as cursor:
                cursor.execute(
                    "SELECT space_id FROM user_spaces WHERE user_id = ? AND active = TRUE", (event.sender,))
                space = cursor.fetchone()

            if not space:
                space = await bot.create_space("GPTBot")
                bot.logger.log(
                    f"Created space {space} for user {event.sender}")

                if bot.logo_uri:
                    await bot.matrix_client.room_put_state(space, "m.room.avatar", {
                        "url": bot.logo_uri
                    }, "")

                with closing(bot.database.cursor()) as cursor:
                    cursor.execute(
                        "INSERT INTO user_spaces (space_id, user_id) VALUES (?, ?)", (space, event.sender))

            else:
                space = space[0]

            response = await bot.matrix_client.room_invite(space, event.sender)

            if isinstance(response, RoomInviteError):
                bot.logger.log(
                    f"Failed to invite user {event.sender} to space {space}", "error")
                await bot.send_message(
                    room, "Sorry, I couldn't invite you to the space. Please try again later.", True)
                return

            bot.database.commit()
            await bot.send_message(room, "Space enabled.", True)
            request = "update"

        elif request.lower() == "disable":
            bot.logger.log("Disabling space...")

            with closing(bot.database.cursor()) as cursor:
                cursor.execute(
                    "SELECT space_id FROM user_spaces WHERE user_id = ? AND active = TRUE", (event.sender,))
                space = cursor.fetchone()[0]

            if not space:
                bot.logger.log(f"User {event.sender} does not have a space")
                await bot.send_message(room, "You don't have a space enabled.", True)
                return

            with closing(bot.database.cursor()) as cursor:
                cursor.execute(
                    "UPDATE user_spaces SET active = FALSE WHERE user_id = ?", (event.sender,))

            bot.database.commit()
            await bot.send_message(room, "Space disabled.", True)
            return

        if request.lower() == "update":
            bot.logger.log("Updating space...")

            with closing(bot.database.cursor()) as cursor:
                cursor.execute(
                    "SELECT space_id FROM user_spaces WHERE user_id = ? AND active = TRUE", (event.sender,))
                space = cursor.fetchone()[0]

            if not space:
                bot.logger.log(f"User {event.sender} does not have a space")
                await bot.send_message(
                    room, "You don't have a space enabled. Create one first using `!gptbot space enable`.", True)
                return

            rooms = bot.matrix_client.rooms

            join_rooms = []

            for room in rooms.values():
                if event.sender in room.users.keys():
                    bot.logger.log(
                        f"Adding room {room.room_id} to space {space}")
                    join_rooms.append(room.room_id)

            await bot.add_rooms_to_space(space, join_rooms)

            if bot.logo_uri:
                await bot.matrix_client.room_put_state(space, "m.room.avatar", {
                    "url": bot.logo_uri
                }, "")

            await bot.send_message(room, "Space updated.", True)
            return

        if request.lower() == "invite":
            bot.logger.log("Inviting user to space...")

            with closing(bot.database.cursor()) as cursor:
                cursor.execute(
                    "SELECT space_id FROM user_spaces WHERE user_id = ?", (event.sender,))
                space = cursor.fetchone()[0]

            if not space:
                bot.logger.log(f"User {event.sender} does not have a space")
                await bot.send_message(
                    room, "You don't have a space enabled. Create one first using `!gptbot space enable`.", True)
                return

            response = await bot.matrix_client.room_invite(space, event.sender)

            if isinstance(response, RoomInviteError):
                bot.logger.log(
                    f"Failed to invite user {user} to space {space}", "error")
                await bot.send_message(
                    room, "Sorry, I couldn't invite you to the space. Please try again later.", True)
                return

            await bot.send_message(room, "Invited you to the space.", True)
            return

    with closing(bot.database.cursor()) as cursor:
        cursor.execute(
            "SELECT active FROM user_spaces WHERE user_id = ?", (event.sender,))
        status = cursor.fetchone()

    if not status:
        await bot.send_message(
            room, "You don't have a space enabled. Create one using `!gptbot space enable`.", True)
        return

    if not status[0]:
        await bot.send_message(
            room, "Your space is disabled. Enable it using `!gptbot space enable`.", True)
        return

    await bot.send_message(
        room, "Your space is enabled. Rooms will be added to it automatically.", True)
    return
