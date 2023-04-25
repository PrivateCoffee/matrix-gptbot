from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_systemmessage(room: MatrixRoom, event: RoomMessageText, bot):
    system_message = " ".join(event.body.split()[2:])

    if system_message:
        bot.logger.log("Adding system message...")

        with bot.database.cursor() as cur:
            cur.execute(
                "INSERT INTO system_messages (room_id, message_id, user_id, body, timestamp) VALUES (?, ?, ?, ?, ?)",
                (room.room_id, event.event_id, event.sender,
                 system_message, event.server_timestamp)
            )

        bot.send_message(room, f"Alright, I've stored the system message: '{system_message}'.", True)
        return

    bot.logger.log("Retrieving system message...")

    system_message = bot.get_system_message(room)

    bot.send_message(room, f"The current system message is: '{system_message}'.", True)
