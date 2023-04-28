import openai
import requests

from .logging import Logger

from typing import Dict, List, Tuple, Generator

class OpenAI:
    api_key: str
    chat_model: str = "gpt-3.5-turbo"
    logger: Logger

    def __init__(self, api_key, chat_model=None, logger=None):
        self.api_key = api_key
        self.chat_model = chat_model or self.chat_model
        self.logger = logger or Logger()

    def generate_chat_response(self, messages: List[Dict[str, str]]) -> Tuple[str, int]:
        """Generate a response to a chat message.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """

        self.logger.log(f"Generating response to {len(messages)} messages using {self.chat_model}...")

        response = openai.ChatCompletion.create(
            model=self.chat_model,
            messages=messages,
            api_key=self.api_key
        )

        result_text = response.choices[0].message['content']
        tokens_used = response.usage["total_tokens"]
        self.logger.log(f"Generated response with {tokens_used} tokens.")
        return result_text, tokens_used

    def generate_image(self, prompt: str) -> Generator[bytes, None, None]:
        """Generate an image from a prompt.

        Args:
            prompt (str): The prompt to use.

        Yields:
            bytes: The image data.
        """

        self.logger.log(f"Generating image from prompt '{prompt}'...")

        response = openai.Image.create(
            prompt=prompt,
            n=1,
            api_key=self.api_key,
            size="1024x1024"
        )

        for image in response.data:
            image = requests.get(image.url).content
            yield image