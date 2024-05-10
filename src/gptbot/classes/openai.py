import openai
import requests
import tiktoken

import asyncio
import json
import base64
import inspect

from functools import partial
from contextlib import closing
from typing import Dict, List, Tuple, Generator, AsyncGenerator, Optional, Any
from io import BytesIO

from pydub import AudioSegment

from .logging import Logger
from ..tools import TOOLS, Handover, StopProcessing

ASSISTANT_CODE_INTERPRETER = [
    {
        "type": "code_interpreter",
    },
]


class AttributeDictionary(dict):
    def __init__(self, *args, **kwargs):
        super(AttributeDictionary, self).__init__(*args, **kwargs)
        self.__dict__ = self


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
    tts_model: str = "tts-1-hd"
    tts_voice: str = "alloy"
    stt_model: str = "whisper-1"

    operator: str = "OpenAI ([https://openai.com](https://openai.com))"

    def __init__(
        self,
        bot,
        api_key,
        chat_model=None,
        image_model=None,
        tts_model=None,
        tts_voice=None,
        stt_model=None,
        base_url=None,
        logger=None,
    ):
        self.bot = bot
        self.api_key = api_key
        self.chat_model = chat_model or self.chat_model
        self.image_model = image_model or self.image_model
        self.logger = logger or bot.logger or Logger()
        self.base_url = base_url or openai.base_url
        self.openai_api = openai.AsyncOpenAI(
            api_key=self.api_key, base_url=self.base_url
        )
        self.tts_model = tts_model or self.tts_model
        self.tts_voice = tts_voice or self.tts_voice
        self.stt_model = stt_model or self.stt_model

    def supports_chat_images(self):
        return "vision" in self.chat_model

    def json_decode(self, data):
        if data.startswith("```json\n"):
            data = data[8:]
        elif data.startswith("```\n"):
            data = data[4:]

        if data.endswith("```"):
            data = data[:-3]

        try:
            return json.loads(data)
        except:
            return False

    async def _request_with_retries(
        self, request: partial, attempts: int = 5, retry_interval: int = 2
    ) -> AsyncGenerator[Any | list | Dict, None]:
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

    async def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        user: Optional[str] = None,
        room: Optional[str] = None,
        allow_override: bool = True,
        use_tools: bool = True,
        model: Optional[str] = None,
    ) -> Tuple[str, int]:
        """Generate a response to a chat message.

        Args:
            messages (List[Dict[str, str]]): A list of messages to use as context.
            user (Optional[str], optional): The user to use the assistant for. Defaults to None.
            room (Optional[str], optional): The room to use the assistant for. Defaults to None.
            allow_override (bool, optional): Whether to allow the chat model to be overridden. Defaults to True.
            use_tools (bool, optional): Whether to use tools. Defaults to True.
            model (Optional[str], optional): The model to use. Defaults to None, which uses the default chat model.

        Returns:
            Tuple[str, int]: The response text and the number of tokens used.
        """
        self.logger.log(
            f"Generating response to {len(messages)} messages for user {user} in room {room}..."
        )

        original_model = chat_model = model or self.chat_model

        # Check current recursion depth to prevent infinite loops

        if use_tools:
            frames = inspect.stack()
            current_function = inspect.getframeinfo(frames[0][0]).function
            count = sum(
                1
                for frame in frames
                if inspect.getframeinfo(frame[0]).function == current_function
            )
            self.logger.log(
                f"{current_function} appears {count} times in the call stack"
            )

            if count > 5:
                self.logger.log(f"Recursion depth exceeded, aborting.")
                return await self.generate_chat_response(
                    messages=messages,
                    user=user,
                    room=room,
                    allow_override=False,  # TODO: Could this be a problem?
                    use_tools=False,
                    model=original_model,
                )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_class.DESCRIPTION,
                    "parameters": tool_class.PARAMETERS,
                },
            }
            for tool_name, tool_class in TOOLS.items()
        ]

        original_messages = messages

        if allow_override and not "gpt-3.5-turbo" in original_model:
            if self.bot.config.getboolean("OpenAI", "ForceTools", fallback=False):
                self.logger.log(f"Overriding chat model to use tools")
                chat_model = "gpt-3.5-turbo"

                out_messages = []

                for message in messages:
                    if isinstance(message, dict):
                        if isinstance(message["content"], str):
                            out_messages.append(message)
                        else:
                            message_content = []
                            for content in message["content"]:
                                if content["type"] == "text":
                                    message_content.append(content)
                            if message_content:
                                message["content"] = message_content
                                out_messages.append(message)
                    else:
                        out_messages.append(message)

                messages = out_messages

        self.logger.log(f"Generating response with model {chat_model}...")

        if (
            use_tools
            and self.bot.config.getboolean("OpenAI", "EmulateTools", fallback=False)
            and not self.bot.config.getboolean("OpenAI", "ForceTools", fallback=False)
            and not "gpt-3.5-turbo" in chat_model
        ):
            self.bot.logger.log("Using tool emulation mode.", "debug")

            messages = (
                [
                    {
                        "role": "system",
                        "content": """You are a tool dispatcher for an AI chat model. You decide which tools to use for the current conversation. You DO NOT RESPOND DIRECTLY TO THE USER. Instead, respond with a JSON object like this:

                    { "type": "tool", "tool": tool_name, "parameters": { "name": "value"  } }

                    - tool_name is the name of the tool you want to use.
                    - parameters is an object containing the parameters for the tool. The parameters are defined in the tool's description.

                    The following tools are available:

                    """
                        + "\n".join(
                            [
                                f"- {tool_name}: {tool_class.DESCRIPTION} ({tool_class.PARAMETERS})"
                                for tool_name, tool_class in TOOLS.items()
                            ]
                        )
                        + """

                        If no tool is required, or all information is already available in the message thread, respond with an empty JSON object: {}

                        Otherwise, respond with a single required tool call. Remember that you DO NOT RESPOND to the user. You MAY ONLY RESPOND WITH JSON OBJECTS CONTAINING TOOL CALLS! DO NOT RESPOND IN NATURAL LANGUAGE.

                        DO NOT include any other text or syntax in your response, only the JSON object. DO NOT surround it in code tags (```). DO NOT, UNDER ANY CIRCUMSTANCES, ASK AGAIN FOR INFORMATION ALREADY PROVIDED IN THE MESSAGES YOU RECEIVED! DO NOT REQUEST MORE INFORMATION THAN ABSOLUTELY REQUIRED TO RESPOND TO THE USER'S MESSAGE! Remind the user that they may ask you to search for additional information if they need it.
                        """,
                    }
                ]
                + messages
            )

        kwargs = {
            "model": chat_model,
            "messages": messages,
            "user": room,
        }

        if "gpt-3.5-turbo" in chat_model and use_tools:
            kwargs["tools"] = tools

        if "gpt-4" in chat_model:
            kwargs["max_tokens"] = self.bot.config.getint(
                "OpenAI", "MaxTokens", fallback=4000
            )

        api_url = self.base_url

        if chat_model.startswith("gpt-"):
            if not self.chat_model.startswith("gpt-"):
                # The model is overridden, we have to ensure that OpenAI is used
                if self.api_key.startswith("sk-"):
                    self.openai_api.base_url = "https://api.openai.com/v1/"

        chat_partial = partial(self.openai_api.chat.completions.create, **kwargs)
        response = await self._request_with_retries(chat_partial)

        # Setting back the API URL to whatever it was before
        self.openai_api.base_url = api_url

        choice = response.choices[0]
        result_text = choice.message.content

        self.logger.log(f"Generated response: {result_text}")

        additional_tokens = 0

        if (not result_text) and choice.message.tool_calls:
            tool_responses = []
            for tool_call in choice.message.tool_calls:
                try:
                    tool_response = await self.bot.call_tool(
                        tool_call, room=room, user=user
                    )
                    if tool_response != False:
                        tool_responses.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_response),
                            }
                        )
                except StopProcessing as e:
                    return (e.args[0] if e.args else False), 0
                except Handover:
                    return await self.generate_chat_response(
                        messages=original_messages,
                        user=user,
                        room=room,
                        allow_override=False,
                        use_tools=False,
                        model=original_model,
                    )

            if not tool_responses:
                self.logger.log(f"No more responses received, aborting.")
                result_text = False
            else:
                try:
                    messages = (
                        original_messages[:-1]
                        + [choice.message]
                        + tool_responses
                        + original_messages[-1:]
                    )
                    result_text, additional_tokens = await self.generate_chat_response(
                        messages=messages, user=user, room=room, model=original_model
                    )
                except openai.APIError as e:
                    if e.code == "max_tokens":
                        self.logger.log(
                            f"Max tokens exceeded, falling back to no-tools response."
                        )
                        try:
                            new_messages = []

                            for message in original_messages:
                                new_message = message

                                if isinstance(message, dict):
                                    if message["role"] == "tool":
                                        new_message["role"] = "system"
                                        del new_message["tool_call_id"]

                                else:
                                    continue

                                new_messages.append(new_message)

                            (
                                result_text,
                                additional_tokens,
                            ) = await self.generate_chat_response(
                                messages=new_messages,
                                user=user,
                                room=room,
                                allow_override=False,
                                use_tools=False,
                                model=original_model,
                            )

                        except openai.APIError as e:
                            if e.code == "max_tokens":
                                (
                                    result_text,
                                    additional_tokens,
                                ) = await self.generate_chat_response(
                                    messages=original_messages,
                                    user=user,
                                    room=room,
                                    allow_override=False,
                                    use_tools=False,
                                    model=original_model,
                                )
                    else:
                        raise e

        elif isinstance((tool_object := self.json_decode(result_text)), dict):
            if "tool" in tool_object:
                tool_name = tool_object["tool"]
                tool_class = TOOLS[tool_name]
                tool_parameters = (
                    tool_object["parameters"] if "parameters" in tool_object else {}
                )

                self.logger.log(
                    f"Using tool {tool_name} with parameters {tool_parameters}..."
                )

                tool_call = AttributeDictionary(
                    {
                        "function": AttributeDictionary(
                            {
                                "name": tool_name,
                                "arguments": json.dumps(tool_parameters),
                            }
                        ),
                    }
                )

                try:
                    tool_response = await self.bot.call_tool(
                        tool_call, room=room, user=user
                    )
                    if tool_response != False:
                        tool_responses = [
                            {
                                "role": "system",
                                "content": str(tool_response),
                            }
                        ]
                except StopProcessing as e:
                    return (e.args[0] if e.args else False), 0
                except Handover:
                    return await self.generate_chat_response(
                        messages=original_messages,
                        user=user,
                        room=room,
                        allow_override=False,
                        use_tools=False,
                        model=original_model,
                    )

                if not tool_responses:
                    self.logger.log(f"No response received, aborting.")
                    result_text = False
                else:
                    try:
                        messages = (
                            original_messages[:-1]
                            + [choice.message]
                            + tool_responses
                            + original_messages[-1:]
                        )
                        (
                            result_text,
                            additional_tokens,
                        ) = await self.generate_chat_response(
                            messages=messages,
                            user=user,
                            room=room,
                            model=original_model,
                        )
                    except openai.APIError as e:
                        if e.code == "max_tokens":
                            (
                                result_text,
                                additional_tokens,
                            ) = await self.generate_chat_response(
                                messages=original_messages,
                                user=user,
                                room=room,
                                allow_override=False,
                                use_tools=False,
                                model=original_model,
                            )
                        else:
                            raise e
            else:
                result_text, additional_tokens = await self.generate_chat_response(
                    messages=original_messages,
                    user=user,
                    room=room,
                    allow_override=False,
                    use_tools=False,
                    model=original_model,
                )

        elif not original_model == chat_model:
            new_messages = []

            for message in original_messages:
                new_message = message

                if isinstance(message, dict):
                    if message["role"] == "tool":
                        new_message["role"] = "system"
                        del new_message["tool_call_id"]

                else:
                    continue

                new_messages.append(new_message)

            result_text, additional_tokens = await self.generate_chat_response(
                messages=new_messages,
                user=user,
                room=room,
                allow_override=False,
                model=original_model,
            )

        try:
            tokens_used = response.usage.total_tokens
        except:
            tokens_used = 0

        self.logger.log(f"Generated response with {tokens_used} tokens.")
        return result_text, tokens_used + additional_tokens

    async def classify_message(
        self, query: str, user: Optional[str] = None
    ) -> Tuple[Dict[str, str], int]:
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
            {"role": "system", "content": system_message},
            {"role": "user", "content": query},
        ]

        self.logger.log(f"Classifying message '{query}'...")

        chat_partial = partial(
            self.openai_api.chat.completions.create,
            model=self.chat_model,
            messages=messages,
            user=str(user),
        )
        response = await self._request_with_retries(chat_partial)

        try:
            result = json.loads(response.choices[0].message["content"])
        except:
            result = {"type": "chat", "prompt": query}

        tokens_used = response.usage["total_tokens"]

        self.logger.log(
            f"Classified message as {result['type']} with {tokens_used} tokens."
        )

        return result, tokens_used

    async def text_to_speech(
        self, text: str, user: Optional[str] = None
    ) -> Generator[bytes, None, None]:
        """Generate speech from text.

        Args:
            text (str): The text to use.

        Yields:
            bytes: The audio data.
        """
        self.logger.log(
            f"Generating speech from text of length: {len(text.split())} words..."
        )

        speech = await self.openai_api.audio.speech.create(
            model=self.tts_model, input=text, voice=self.tts_voice
        )

        return speech.content

    async def speech_to_text(
        self, audio: bytes, user: Optional[str] = None
    ) -> Tuple[str, int]:
        """Generate text from speech.

        Args:
            audio (bytes): The audio data.

        Returns:
            Tuple[str, int]: The text and the number of tokens used.
        """
        self.logger.log(f"Generating text from speech...")

        audio_file = BytesIO()
        AudioSegment.from_file(BytesIO(audio)).export(audio_file, format="mp3")
        audio_file.name = "audio.mp3"

        response = await self.openai_api.audio.transcriptions.create(
            model=self.stt_model,
            file=audio_file,
        )

        text = response.text

        self.logger.log(f"Recognized text: {len(text.split())} words.")

        return text

    async def generate_image(
        self, prompt: str, user: Optional[str] = None, orientation: str = "square"
    ) -> Generator[bytes, None, None]:
        """Generate an image from a prompt.

        Args:
            prompt (str): The prompt to use.
            user (Optional[str], optional): The user to use the assistant for. Defaults to None.
            orientation (str, optional): The orientation of the image. Defaults to "square".

        Yields:
            bytes: The image data.
        """
        self.logger.log(f"Generating image from prompt '{prompt}'...")

        split_prompt = prompt.split()
        delete_first = False

        size = "1024x1024"

        if self.image_model == "dall-e-3":
            if orientation == "portrait" or (
                delete_first := split_prompt[0] == "--portrait"
            ):
                size = "1024x1792"
            elif orientation == "landscape" or (
                delete_first := split_prompt[0] == "--landscape"
            ):
                size = "1792x1024"

        if delete_first:
            prompt = " ".join(split_prompt[1:])

        self.logger.log(
            f"Generating image with size {size} using model {self.image_model}..."
        )

        args = {
            "model": self.image_model,
            "quality": "standard" if self.image_model != "dall-e-3" else "hd",
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

        if user:
            args["user"] = user

        image_partial = partial(self.openai_api.images.generate, **args)
        response = await self._request_with_retries(image_partial)

        images = []

        for image in response.data:
            image = requests.get(image.url).content
            images.append(image)

        return images, len(images)

    async def describe_images(
        self, messages: list, user: Optional[str] = None
    ) -> Tuple[str, int]:
        """Generate a description for an image.

        Args:
            image (bytes): The image data.

        Returns:
            Tuple[str, int]: The description and the number of tokens used.
        """
        self.logger.log(f"Generating description for images in conversation...")

        system_message = "You are an image description generator. You generate descriptions for all images in the current conversation, one after another."

        messages = [{"role": "system", "content": system_message}] + messages[1:]

        if not "vision" in (chat_model := self.chat_model):
            chat_model = self.chat_model + "gpt-4-vision-preview"

        chat_partial = partial(
            self.openai_api.chat.completions.create,
            model=self.chat_model,
            messages=messages,
            user=str(user),
        )

        response = await self._request_with_retries(chat_partial)

        return response.choices[0].message.content, response.usage.total_tokens
