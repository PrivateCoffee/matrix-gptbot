from ...classes.logging import Logger

import asyncio
import json
from functools import partial
from typing import Any, AsyncGenerator, Dict, Optional, Mapping


class AttributeDictionary(dict):
    def __init__(self, *args, **kwargs):
        super(AttributeDictionary, self).__init__(*args, **kwargs)
        self.__dict__ = self


class BaseAI:
    bot: Any
    logger: Logger

    def __init__(self, bot, config: Mapping, logger: Optional[Logger] = None):
        self.bot = bot
        self.logger = logger or bot.logger or Logger()
        self._config = config

    @property
    def chat_api(self) -> str:
        return self.chat_model

    async def _request_with_retries(
        self, request: partial, attempts: int = 5, retry_interval: int = 2
    ) -> AsyncGenerator[Any | list | Dict, None]:
        """Retry a request a set number of times if it fails.

        Args:
            request (partial): The request to make with retries.
            attempts (int, optional): The number of attempts to make. Defaults to 5.
            retry_interval (int, optional): The interval in seconds between attempts. Defaults to 2 seconds.

        Returns:
            AsyncGenerator[Any | list | Dict, None]: The response for the request.
        """
        current_attempt = 1
        while current_attempt <= attempts:
            try:
                response = await request()
                return response
            except Exception as e:
                self.logger.log(f"Request failed: {e}", "error")
                self.logger.log(f"Retrying in {retry_interval} seconds...")
                await asyncio.sleep(retry_interval)
                current_attempt += 1

        raise Exception("Request failed after all attempts.")
