from .base import BaseAI
from ..logging import Logger

from typing import Optional, Mapping, List, Dict, Tuple

import google.generativeai as genai


class GeminiAI(BaseAI):
    api_code: str = "google"

    @property
    def chat_api(self) -> str:
        return self.chat_model

    google_api: genai.GenerativeModel

    operator: str = "Google (https://ai.google)"

    def __init__(
        self,
        bot,
        config: Mapping,
        logger: Optional[Logger] = None,
    ):
        super().__init__(bot, config, logger)
        genai.configure(api_key=self.api_key)
        self.gemini_api = genai.GenerativeModel(self.chat_model)

    @property
    def api_key(self):
        return self._config["APIKey"]

    @property
    def chat_model(self):
        return self._config.get("Model", fallback="gemini-pro")

    def prepare_messages(event, messages: List[Dict[str, str]], ) -> List[str]:
        return [message["content"] for message in messages]

    async def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        user: Optional[str] = None,
        room: Optional[str] = None,
        use_tools: bool = True,
        model: Optional[str] = None,
    ) -> Tuple[str, int]:
        """Generate a response to a chat message.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.
            user (Optional[str], optional): The user to use the assistant for. Defaults to None.
            room (Optional[str], optional): The room to use the assistant for. Defaults to None.
            use_tools (bool, optional): Whether to use tools. Defaults to True.
            model (Optional[str], optional): The model to use. Defaults to None, which uses the default chat model.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """
        self.logger.log(
            f"Generating response to {len(messages)} messages for user {user} in room {room}..."
        )

        messages = self.prepare_messages(messages)

        return self.gemini_api.generate_content(
            messages=messages,
            user=user,
            room=room,
            use_tools=use_tools,
            model=model,
        )
