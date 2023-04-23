from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

from random import SystemRandom


async def command_coin(room: MatrixRoom, event: RoomMessageText, context: dict):
    context["logger"]("Flipping a coin...")

    heads = SystemRandom().choice([True, False])

    return room.room_id, "m.room.message", {"msgtype": "m.notice",
                                            "body": "Heads!" if heads else "Tails!"}
