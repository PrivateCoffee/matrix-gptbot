import openai
import requests

import asyncio
import json
from functools import partial
from contextlib import closing

from .logging import Logger

from typing import Dict, List, Tuple, Generator, AsyncGenerator, Optional, Any

ASSISTANT_CODE_INTERPRETER = [
    {
        "type": "code_interpreter",
    },

]

class OpenAI:
    api_key: str
    chat_model: str = "gpt-3.5-turbo"
    logger: Logger

    api_code: str = "openai"

    @property
    def chat_api(self) -> str:
        return self.chat_model

    classification_api = chat_api
    image_model: str = "dall-e-2"

    operator: str = "OpenAI ([https://openai.com](https://openai.com))"

    def __init__(self, bot, api_key, chat_model=None, image_model=None, base_url=None, logger=None):
        self.bot = bot
        self.api_key = api_key
        self.chat_model = chat_model or self.chat_model
        self.image_model = image_model or self.image_model
        self.logger = logger or Logger()
        self.base_url = base_url or openai.base_url
        self.openai_api = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def supports_chat_images(self):
        return "vision" in self.chat_model

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

    async def create_assistant(self, system_message: str, tools: List[Dict[str, str]] = ASSISTANT_CODE_INTERPRETER) -> str:
        """Create a new assistant.

        Args:
            system_message (str): The system message to use.
            tools (List[Dict[str, str]], optional): The tools to use. Defaults to ASSISTANT_CODE_INTERPRETER.

        Returns:
            str: The assistant ID.
        """
        self.logger.log(f"Creating assistant with {len(tools)} tools...")
        assistant_partial = partial(
            self.openai_api.beta.assistants.create,
                model=self.chat_model,
                instructions=system_message,
                tools=tools
        )
        response = await self._request_with_retries(assistant_partial)
        assistant_id = response.id
        self.logger.log(f"Created assistant with ID {assistant_id}.")
        return assistant_id

    async def create_thread(self):
        # TODO: Implement
        pass

    async def setup_assistant(self, room: str, system_message: str, tools: List[Dict[str, str]] = ASSISTANT_CODE_INTERPRETER) -> Tuple[str, str]:
        """Create a new assistant and set it up for a room.

        Args:
            room (str): The room to set up the assistant for.
            system_message (str): The system message to use.
            tools (List[Dict[str, str]], optional): The tools to use. Defaults to ASSISTANT_CODE_INTERPRETER.

        Returns:
            Tuple[str, str]: The assistant ID and the thread ID.
        """
        assistant_id = await self.create_assistant(system_message, tools)
        thread_id = await self.create_thread() # TODO: Adapt to actual implementation

        self.logger.log(f"Setting up assistant {assistant_id} with thread {thread_id} for room {room}...")

        with closing(self.bot.database.cursor()) as cursor:
            cursor.execute("INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)", (room, "openai_assistant", assistant_id))
            cursor.execute("INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)", (room, "openai_thread", thread_id))
            self.bot.database.commit()

        return assistant_id, thread_id

    async def generate_assistant_response(self, messages: List[Dict[str, str]], room: str, user: Optional[str] = None) -> Tuple[str, int]:
        """Generate a response to a chat message using an assistant.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.
            room (str): The room to use the assistant for.
            user (Optional[str], optional): The user to use the assistant for. Defaults to None.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """
        
        self.openai_api.beta.threads.messages.create(
            thread_id=self.get_thread_id(room),
            messages=messages,
            user=user
        )

    async def generate_chat_response(self, messages: List[Dict[str, str]], user: Optional[str] = None, room: Optional[str] = None) -> Tuple[str, int]:
        """Generate a response to a chat message.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.
            user (Optional[str], optional): The user to use the assistant for. Defaults to None.
            room (Optional[str], optional): The room to use the assistant for. Defaults to None.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """
        self.logger.log(f"Generating response to {len(messages)} messages using {self.chat_model}...")

        if self.room_uses_assistant(room):
            return await self.generate_assistant_response(messages, room, user)

        chat_partial = partial(
            self.openai_api.chat.completions.create,
                model=self.chat_model,
                messages=messages,
                user=user,
                max_tokens=4096
        )
        response = await self._request_with_retries(chat_partial)

        result_text = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
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
            self.openai_api.chat.completions.create,
                model=self.chat_model,
                messages=messages,
                user=user,
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
            self.openai_api.images.generate,
                model=self.image_model,
                prompt=prompt,
                n=1,
                size="1024x1024",
                user=user,
        )
        response = await self._request_with_retries(image_partial)

        images = []

        for image in response.data:
            image = requests.get(image.url).content
            images.append(image)

        return images, len(images)
