from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

from random import SystemRandom


async def command_dice(room: MatrixRoom, event: RoomMessageText, bot):
    bot.logger.log("Rolling a dice...")

    try:
        sides = int(event.body.split()[2])
    except ValueError:
        sides = 6

    if sides < 2:
        await bot.send_message(room, f"A dice with {sides} sides? How would that work?", True)

    else:
        result = SystemRandom().randint(1, sides)
        body = f"Rolling a {sides}-sided dice... It's a {result}!"

    await bot.send_message(room, body, True)