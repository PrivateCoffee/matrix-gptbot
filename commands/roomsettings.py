from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_roomsettings(room: MatrixRoom, event: RoomMessageText, bot):
    setting = event.body.split()[2]
    value = " ".join(event.body.split()[3:]) if len(
        event.body.split()) > 3 else None

    if setting == "system_message":
        if value:
            bot.logger.log("Adding system message...")

            with bot.database.cursor() as cur:
                cur.execute(
                    """INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)
                    ON CONFLICT (room_id, setting) DO UPDATE SET value = ?;""",
                    (room.room_id, "system_message", value, value)
                )

            await bot.send_message(room, f"Alright, I've stored the system message: '{value}'.", True)
            return

        bot.logger.log("Retrieving system message...")

        system_message = bot.get_system_message(room)

        await bot.send_message(room, f"The current system message is: '{system_message}'.", True)
        return

    if setting == "classification":
        if value:
            if value.lower() in ["true", "false"]:
                value = value.lower() == "true"

                bot.logger.log("Setting classification status...")

                with bot.database.cursor() as cur:
                    cur.execute(
                        """INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)
                        ON CONFLICT (room_id, setting) DO UPDATE SET value = ?;""",
                        (room.room_id, "use_classification", "1" if value else "0", "1" if value else "0")
                    )

                await bot.send_message(room, f"Alright, I've set use_classification to: '{value}'.", True)
                return

            await bot.send_message(room, "You need to provide a boolean value (true/false).", True)
            return

        bot.logger.log("Retrieving classification status...")

        use_classification = await bot.room_uses_classification(room)

        await bot.send_message(room, f"The current classification status is: '{use_classification}'.", True)
        return

    message = f"""
    The following settings are available:

    - system_message [message]: Get or set the system message to be sent to the chat model
    - classification [true/false]: Get or set whether the room uses classification
    """

    await bot.send_message(room, message, True)
