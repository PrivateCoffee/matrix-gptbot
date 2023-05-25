async def test_response_callback(response, bot):
    bot.logger.log(
        f"{response.__class__} response received", "debug")
    