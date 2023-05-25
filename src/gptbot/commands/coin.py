from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

from random import SystemRandom


async def command_coin(room: MatrixRoom, event: RoomMessageText, bot):
    bot.logger.log("Flipping a coin...")

    heads = SystemRandom().choice([True, False])
    body = "Flipping a coin... It's " + ("heads!" if heads else "tails!")

    await bot.send_message(room, body, True)