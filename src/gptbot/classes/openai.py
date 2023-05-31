import openai
import requests

import asyncio
import json
from functools import partial

from .logging import Logger

from typing import Dict, List, Tuple, Generator, AsyncGenerator, Optional, Any

class OpenAI:
    api_key: str
    chat_model: str = "gpt-3.5-turbo"
    logger: Logger

    api_code: str = "openai"

    @property
    def chat_api(self) -> str:
        return self.chat_model

    classification_api = chat_api
    image_api: str = "dalle"

    operator: str = "OpenAI ([https://openai.com](https://openai.com))"

    def __init__(self, api_key, chat_model=None, logger=None):
        self.api_key = api_key
        self.chat_model = chat_model or self.chat_model
        self.logger = logger or Logger()
        self.base_url = openai.api_base

    async def _request_with_retries(self, request: partial, attempts: int = 5, retry_interval: int = 2) -> AsyncGenerator[Any | list | Dict, None]:
        """Retry a request a set number of times if it fails.

        Args:
            request (partial): The request to make with retries.
            attempts (int, optional): The number of attempts to make. Defaults to 5.
            retry_interval (int, optional): The interval in seconds between attempts. Defaults to 2 seconds.

        Returns:
            AsyncGenerator[Any | list | Dict, None]: The OpenAI response for the request.
        """
        # call the request function and return the response if it succeeds, else retry
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

        # if all attempts failed, raise an exception
        raise Exception("Request failed after all attempts.")

    async def generate_chat_response(self, messages: List[Dict[str, str]], user: Optional[str] = None) -> Tuple[str, int]:
        """Generate a response to a chat message.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """
        self.logger.log(f"Generating response to {len(messages)} messages using {self.chat_model}...")


        chat_partial = partial(
            openai.ChatCompletion.acreate,
                model=self.chat_model,
                messages=messages,
                api_key=self.api_key,
                user=user,
                api_base=self.base_url,
        )
        response = await self._request_with_retries(chat_partial)


        result_text = response.choices[0].message['content']
        tokens_used = response.usage["total_tokens"]
        self.logger.log(f"Generated response with {tokens_used} tokens.")
        return result_text, tokens_used

    async def classify_message(self, query: str, user: Optional[str] = None) -> Tuple[Dict[str, str], int]:
        system_message = """You are a classifier for different types of messages. You decide whether an incoming message is meant to be a prompt for an AI chat model, or meant for a different API. You respond with a JSON object like this:

{ "type": event_type, "prompt": prompt }

- If the message you received is meant for the AI chat model, the event_type is "chat", and the prompt is the literal content of the message you received. This is also the default if none of the other options apply.
- If it is a prompt for a calculation that can be answered better by WolframAlpha than an AI chat bot, the event_type is "calculate". Optimize the message you received for input to WolframAlpha, and return it as the prompt attribute.
- If it is a prompt for an AI image generation, the event_type is "imagine". Optimize the message you received for use with DALL-E, and return it as the prompt attribute.
- If the user is asking you to create a new room, the event_type is "newroom", and the prompt is the name of the room, if one is given, else an empty string.
- If the user is asking you to throw a coin, the event_type is "coin". The prompt is an empty string.
- If the user is asking you to roll a dice, the event_type is "dice". The prompt is an string containing an optional number of sides, if one is given, else an empty string.
- If for any reason you are unable to classify the message (for example, if it infringes on your terms of service), the event_type is "error", and the prompt is a message explaining why you are unable to process the message.

Only the event_types mentioned above are allowed, you must not respond in any other way."""
        messages = [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": query
            }
        ]

        self.logger.log(f"Classifying message '{query}'...")

        chat_partial = partial(
            openai.ChatCompletion.acreate,
                model=self.chat_model,
                messages=messages,
                api_key=self.api_key,
                user=user,
                api_base=self.base_url,
        )
        response = await self._request_with_retries(chat_partial)

        try:
            result = json.loads(response.choices[0].message['content'])
        except:
            result = {"type": "chat", "prompt": query}

        tokens_used = response.usage["total_tokens"]

        self.logger.log(f"Classified message as {result['type']} with {tokens_used} tokens.")

        return result, tokens_used

    async def generate_image(self, prompt: str, user: Optional[str] = None) -> Generator[bytes, None, None]:
        """Generate an image from a prompt.

        Args:
            prompt (str): The prompt to use.

        Yields:
            bytes: The image data.
        """
        self.logger.log(f"Generating image from prompt '{prompt}'...")

        image_partial = partial(
            openai.Image.acreate,
                prompt=prompt,
                n=1,
                api_key=self.api_key,
                size="1024x1024",
                user=user,
                api_base=self.base_url,
        )
        response = await self._request_with_retries(image_partial)

        images = []

        for image in response.data:
            image = requests.get(image.url).content
            images.append(image)

        return images, len(images)
