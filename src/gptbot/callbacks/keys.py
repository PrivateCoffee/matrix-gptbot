from nio.crypto.device import OlmDevice

async def keys_query_callback(response, bot):
    bot.matrix_client.receive_response(response)
    try:
        for user_id, device_dict in response.device_keys.items():
            for device_id, keys in device_dict.items():
                bot.logger.log(f"New keys for {device_id} from {user_id}: {keys}", "info")
                device = OlmDevice(user_id, device_id, keys)
                await bot.matrix_client.verify_device(device)

    except Exception as e:
        bot.logger.log(f"Error handling KeysQueryResponse: {e}", "error")
        raise
