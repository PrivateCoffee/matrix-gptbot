from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

from contextlib import closing


async def command_stats(room: MatrixRoom, event: RoomMessageText, bot):
    await bot.send_message(
        room,
        "The `stats` command is no longer supported. Sorry for the inconvenience.",
        True,
    )
    return

    # Yes, the code below is unreachable, but it's kept here for reference.

    bot.logger.log("Showing stats...")

    if not bot.database:
        bot.logger.log("No database connection - cannot show stats")
        await bot.send_message(
            room,
            "Sorry, I'm not connected to a database, so I don't have any statistics on your usage.",
            True,
        )
        return

    with closing(bot.database.cursor()) as cursor:
        cursor.execute(
            "SELECT SUM(tokens) FROM token_usage WHERE room_id = ?", (room.room_id,)
        )
        total_tokens = cursor.fetchone()[0] or 0

    await bot.send_message(room, f"Total tokens used: {total_tokens}", True)
