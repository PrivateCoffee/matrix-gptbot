async def sync_callback(response, bot):
    bot.logger.log(
        f"Sync response received (next batch: {response.next_batch})", "debug")
    SYNC_TOKEN = response.next_batch

    bot.sync_token = SYNC_TOKEN

    await bot.accept_pending_invites()