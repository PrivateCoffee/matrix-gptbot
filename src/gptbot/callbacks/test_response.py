from nio import ErrorResponse


async def test_response_callback(response, bot):
    if isinstance(response, ErrorResponse):
        bot.logger.log(
            f"Error response received ({response.__class__.__name__}): {response.message}",
            "warning",
        )
    else:
        bot.logger.log(f"{response.__class__} response received", "debug")
