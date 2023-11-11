from nio import MatrixRoom, RoomMessageText

from datetime import datetime

async def message_callback(room: MatrixRoom | str, event: RoomMessageText, bot):
    bot.logger.log(f"Received message from {event.sender} in room {room.room_id}")

    sent = datetime.fromtimestamp(event.server_timestamp / 1000)
    received = datetime.now()
    latency = received - sent

    if event.sender == bot.matrix_client.user_id:
        bot.logger.log("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot") or event.body.startswith("* !gptbot"):
        await bot.process_command(room, event)

    elif event.body.startswith("!"):
        bot.logger.log(f"Received {event.body} - might be a command, but not for this bot - ignoring")

    else:
        await bot.process_query(room, event)

    processed = datetime.now()
    processing_time = processed - received

    bot.logger.log(f"Message processing took {processing_time.total_seconds()} seconds (latency: {latency.total_seconds()} seconds)")

    if bot.room_uses_timing(room):
        await bot.send_message(room, f"Message processing took {processing_time.total_seconds()} seconds (latency: {latency.total_seconds()} seconds)", True)