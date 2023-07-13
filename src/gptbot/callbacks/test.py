from mautrix.types import Event

async def test_callback(event: Event, bot):
    """Test callback for debugging purposes.

    Args:
        event (Event): The event that was sent.
    """

    bot.logger.log(f"Test callback called: {event.room_id} {event.event_id} {event.sender} {event.__class__}")