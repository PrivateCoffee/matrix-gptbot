from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_parcel(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = event.body.split()[2:]

    if prompt:
        bot.logger.log("Looking up parcels...")

        for parcel in prompt:
            status, tokens_used = bot.parcel_api.lookup_parcel(parcel, user=room.room_id)

            await bot.send_message(room, status, True)

            bot.log_api_usage(event, room, f"{bot.parcel_api.api_code}-{bot.parcel_api.parcel_api}", tokens_used)
            return

    await bot.send_message(room, "You need to provide tracking numbers.", True)