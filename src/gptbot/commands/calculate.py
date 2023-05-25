from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom


async def command_calculate(room: MatrixRoom, event: RoomMessageText, bot):
    prompt = event.body.split()[2:]
    text = False
    results_only = True

    if "--text" in prompt:
        text = True
        delete = prompt.index("--text")
        del prompt[delete]

    if "--details" in prompt:
        results_only = False
        delete = prompt.index("--details")
        del prompt[delete]

    prompt = " ".join(prompt)

    if prompt:
        bot.logger.log("Querying calculation API...")

        for subpod in bot.calculation_api.generate_calculation_response(prompt, text, results_only, user=room.room_id):
            bot.logger.log(f"Sending subpod...")
            if isinstance(subpod, bytes):
                await bot.send_image(room, subpod)
            else:
                await bot.send_message(room, subpod, True)

        bot.log_api_usage(event, room, f"{bot.calculation_api.api_code}-{bot.calculation_api.calculation_api}", tokens_used)

        return

    await bot.send_message(room, "You need to provide a prompt.", True)