from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_roomsettings(room: MatrixRoom, event: RoomMessageText, bot):
    setting = event.body.split()[2] if len(event.body.split()) > 2 else None
    value = " ".join(event.body.split()[3:]) if len(
        event.body.split()) > 3 else None

    if setting in ("classification", "timing"):
        setting = f"use_{setting}"
    if setting == "systemmessage":
        setting = "system_message"

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

    if setting in ("use_classification", "always_reply", "use_timing"):
        if value:
            if value.lower() in ["true", "false"]:
                value = value.lower() == "true"

                bot.logger.log(f"Setting {setting} status for {room.room_id} to {value}...")

                with bot.database.cursor() as cur:
                    cur.execute(
                        """INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)
                        ON CONFLICT (room_id, setting) DO UPDATE SET value = ?;""",
                        (room.room_id, setting, "1" if value else "0", "1" if value else "0")
                    )

                await bot.send_message(room, f"Alright, I've set {setting} to: '{value}'.", True)
                return

            await bot.send_message(room, "You need to provide a boolean value (true/false).", True)
            return

        bot.logger.log(f"Retrieving {setting} status for {room.room_id}...")

        with bot.database.cursor() as cur:
            cur.execute(
                """SELECT value FROM room_settings WHERE room_id = ? AND setting = ?;""",
                (room.room_id, setting)
            )

            value = cur.fetchone()[0]

            if not value:
                if setting in ("use_classification", "use_timing"):
                    value = False
                elif setting == "always_reply":
                    value = True
            else:
                value = bool(int(value))

        await bot.send_message(room, f"The current {setting} status is: '{value}'.", True)
        return

    message = f"""The following settings are available:

- system_message [message]: Get or set the system message to be sent to the chat model
- classification [true/false]: Get or set whether the room uses classification
- always_reply [true/false]: Get or set whether the bot should reply to all messages (if false, only reply to mentions and commands)
"""

    await bot.send_message(room, message, True)
