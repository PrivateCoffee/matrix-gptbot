from nio import MatrixRoom, Event

async def test_callback(room: MatrixRoom, event: Event, bot):
    """Test callback for debugging purposes.

    Args:
        room (MatrixRoom): The room the event was sent in.
        event (Event): The event that was sent.
    """

    bot.logger.log(f"Test callback called: {room.room_id} {event.event_id} {event.sender} {event.__class__}")