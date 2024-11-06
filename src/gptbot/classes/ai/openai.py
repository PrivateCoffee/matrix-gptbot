import openai
import requests
import tiktoken

import base64
import json
import inspect

from functools import partial
from typing import Dict, List, Tuple, Generator, Optional, Mapping, Any
from io import BytesIO

from pydub import AudioSegment
from PIL import Image
from nio import (
    RoomMessageNotice,
    RoomMessageText,
    RoomMessageAudio,
    RoomMessageFile,
    RoomMessageImage,
    RoomMessageVideo,
    Event,
)

from ..logging import Logger
from ...tools import TOOLS, Handover, StopProcessing
from ..exceptions import DownloadException
from .base import BaseAI, AttributeDictionary

ASSISTANT_CODE_INTERPRETER = [
    {
        "type": "code_interpreter",
    },
]


class OpenAI(BaseAI):
    api_code: str = "openai"

    @property
    def chat_api(self) -> str:
        return self.chat_model

    openai_api: openai.AsyncOpenAI

    operator: str = "OpenAI ([https://openai.com](https://openai.com))"

    def __init__(
        self,
        bot,
        config: Mapping,
        logger: Optional[Logger] = None,
    ):
        super().__init__(bot, config, logger)
        self.openai_api = openai.AsyncOpenAI(
            api_key=self.api_key, base_url=self.base_url
        )

    # TODO: Add descriptions for these properties

    @property
    def api_key(self):
        return self._config["APIKey"]

    @property
    def chat_model(self):
        return self._config.get("Model", fallback="gpt-4o")

    @property
    def image_model(self):
        return self._config.get("ImageModel", fallback="dall-e-3")

    @property
    def tts_model(self):
        return self._config.get("TTSModel", fallback="tts-1-hd")

    @property
    def tts_voice(self):
        return self._config.get("TTSVoice", fallback="alloy")

    @property
    def stt_model(self):
        return self._config.get("STTModel", fallback="whisper-1")

    @property
    def base_url(self):
        return self._config.get("BaseURL", fallback="https://api.openai.com/v1/")

    @property
    def temperature(self):
        return self._config.getfloat("Temperature", fallback=1.0)

    @property
    def top_p(self):
        return self._config.getfloat("TopP", fallback=1.0)

    @property
    def frequency_penalty(self):
        return self._config.getfloat("FrequencyPenalty", fallback=0.0)

    @property
    def presence_penalty(self):
        return self._config.getfloat("PresencePenalty", fallback=0.0)

    @property
    def force_vision(self):
        return self._config.getboolean("ForceVision", fallback=False)

    @property
    def force_video_input(self):
        return self._config.getboolean("ForceVideoInput", fallback=False)

    @property
    def force_tools(self):
        return self._config.getboolean("ForceTools", fallback=False)

    @property
    def tool_model(self):
        return self._config.get("ToolModel")

    @property
    def vision_model(self):
        return self._config.get("VisionModel")

    @property
    def emulate_tools(self):
        return self._config.getboolean("EmulateTools", fallback=False)

    @property
    def max_tokens(self):
        # TODO: This should be model-specific
        return self._config.getint("MaxTokens", fallback=4000)

    @property
    def max_messages(self):
        return self._config.getint("MaxMessages", fallback=30)

    @property
    def max_image_long_side(self):
        return self._config.getint("MaxImageLongSide", fallback=2000)

    @property
    def max_image_short_side(self):
        return self._config.getint("MaxImageShortSide", fallback=768)

    def _is_tool_model(self, model: str) -> bool:
        return model in ("gpt-3.5-turbo", "gpt-4-turbo", "gpt-4o")

    def _is_vision_model(self, model: str) -> bool:
        return model in ("gpt-4-turbo", "gpt-4o") or "vision" in model

    def supports_chat_images(self):
        return self._is_vision_model(self.chat_model) or self.force_vision

    def supports_chat_videos(self):
        return self.force_video_input

    def json_decode(self, data):
        if data.startswith("```json\n"):
            data = data[8:]
        elif data.startswith("```\n"):
            data = data[4:]

        if data.endswith("```"):
            data = data[:-3]

        try:
            return json.loads(data)
        except Exception:
            return False

    async def prepare_messages(
        self,
        event: Event,
        messages: List[Dict[str, str]],
        system_message=None,
        room=None,
    ) -> List[Any]:
        chat_messages = []

        self.logger.log(f"Incoming messages: {messages}", "debug")

        messages.append(event)

        for message in messages:
            if isinstance(message, (RoomMessageNotice, RoomMessageText)):
                role = (
                    "assistant"
                    if message.sender == self.bot.matrix_client.user_id
                    else "user"
                )
                if message == event or (not message.event_id == event.event_id):
                    message_body = (
                        message.body
                        if not self.supports_chat_images()
                        else [{"type": "text", "text": message.body}]
                    )
                    chat_messages.append({"role": role, "content": message_body})

            elif isinstance(message, RoomMessageAudio) or (
                isinstance(message, RoomMessageFile) and message.body.endswith(".mp3")
            ):
                role = (
                    "assistant"
                    if message.sender == self.bot.matrix_client.user_id
                    else "user"
                )
                if message == event or (not message.event_id == event.event_id):
                    if room and self.room_uses_stt(room):
                        try:
                            download = await self.bot.download_file(
                                message.url, raise_error=True
                            )
                            message_text = await self.bot.stt_api.speech_to_text(
                                download.body
                            )
                        except Exception as e:
                            self.logger.log(
                                f"Error generating text from audio: {e}", "error"
                            )
                            message_text = message.body
                    else:
                        message_text = message.body

                    message_body = (
                        message_text
                        if not self.supports_chat_images()
                        else [{"type": "text", "text": message_text}]
                    )
                    chat_messages.append({"role": role, "content": message_body})

            elif isinstance(message, RoomMessageFile):
                try:
                    download = await self.bot.download_file(
                        message.url, raise_error=True
                    )
                    if download:
                        try:
                            text = download.body.decode("utf-8")
                        except UnicodeDecodeError:
                            text = None

                        if text:
                            role = (
                                "assistant"
                                if message.sender == self.bot.matrix_client.user_id
                                else "user"
                            )
                            if message == event or (
                                not message.event_id == event.event_id
                            ):
                                message_body = (
                                    text
                                    if not self.supports_chat_images()
                                    else [{"type": "text", "text": text}]
                                )
                                chat_messages.append(
                                    {"role": role, "content": message_body}
                                )

                except Exception as e:
                    self.logger.log(f"Error generating text from file: {e}", "error")
                    message_body = (
                        message.body
                        if not self.supports_chat_images()
                        else [{"type": "text", "text": message.body}]
                    )
                    chat_messages.append({"role": "system", "content": message_body})

            elif self.supports_chat_images() and isinstance(message, RoomMessageImage):
                try:
                    image_url = message.url
                    download = await self.bot.download_file(image_url, raise_error=True)

                    if download:
                        pil_image = Image.open(BytesIO(download.body))

                        file_format = pil_image.format or "PNG"

                        max_long_side = self.max_image_long_side
                        max_short_side = self.max_image_short_side

                        if max_long_side and max_short_side:
                            if pil_image.width > pil_image.height:
                                if pil_image.width > max_long_side:
                                    pil_image.thumbnail((max_long_side, max_short_side))

                            else:
                                if pil_image.height > max_long_side:
                                    pil_image.thumbnail((max_short_side, max_long_side))

                        bio = BytesIO()

                        pil_image.save(bio, format=file_format)

                        encoded_url = f"data:{download.content_type};base64,{base64.b64encode(bio.getvalue()).decode('utf-8')}"
                        parent = (
                            chat_messages[-1]
                            if chat_messages
                            and chat_messages[-1]["role"]
                            == (
                                "assistant"
                                if message.sender == self.bot.matrix_client.user_id
                                else "user"
                            )
                            else None
                        )

                        if not parent:
                            chat_messages.append(
                                {
                                    "role": (
                                        "assistant"
                                        if message.sender == self.matrix_client.user_id
                                        else "user"
                                    ),
                                    "content": [],
                                }
                            )
                            parent = chat_messages[-1]

                        parent["content"].append(
                            {"type": "image_url", "image_url": {"url": encoded_url}}
                        )

                except Exception as e:
                    if room and isinstance(e, DownloadException):
                        self.bot.send_message(
                            room,
                            f"Could not process image due to download error: {e.args[0]}",
                            True,
                        )

                    self.logger.log(f"Error generating image from file: {e}", "error")
                    message_body = (
                        message.body
                        if not self.supports_chat_images()
                        else [{"type": "text", "text": message.body}]
                    )
                    chat_messages.append({"role": "system", "content": message_body})

            elif self.supports_chat_videos() and (
                isinstance(message, RoomMessageVideo)
                or (
                    isinstance(message, RoomMessageFile)
                    and message.body.endswith(".mp4")
                )
            ):
                try:
                    video_url = message.url
                    download = await self.bot.download_file(video_url, raise_error=True)

                    if download:
                        video = BytesIO(download.body)
                        video_url = f"data:{download.content_type};base64,{base64.b64encode(video.getvalue()).decode('utf-8')}"

                        parent = (
                            chat_messages[-1]
                            if chat_messages
                            and chat_messages[-1]["role"]
                            == (
                                "assistant"
                                if message.sender == self.bot.matrix_client.user_id
                                else "user"
                            )
                            else None
                        )

                        if not parent:
                            chat_messages.append(
                                {
                                    "role": (
                                        "assistant"
                                        if message.sender == self.matrix_client.user_id
                                        else "user"
                                    ),
                                    "content": [],
                                }
                            )
                            parent = chat_messages[-1]

                        parent["content"].append(
                            {"type": "image_url", "image_url": {"url": video_url}}
                        )

                except Exception as e:
                    if room and isinstance(e, DownloadException):
                        self.bot.send_message(
                            room,
                            f"Could not process video due to download error: {e.args[0]}",
                            True,
                        )

                    self.logger.log(f"Error generating video from file: {e}", "error")
                    message_body = (
                        message.body
                        if not self.supports_chat_images()
                        else [{"type": "text", "text": message.body}]
                    )
                    chat_messages.append({"role": "system", "content": message_body})

        self.logger.log(f"Prepared messages: {chat_messages}", "debug")

        # Truncate messages to fit within the token limit
        chat_messages = self._truncate(
            messages=chat_messages,
            max_tokens=self.max_tokens - 1,
            system_message=system_message,
        )

        return chat_messages

    def _truncate(
        self,
        messages: List[Any],
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
    ) -> List[Any]:
        """Truncate messages to fit within the token limit.

        Args:
            messages (List[Any]): The messages to truncate.
            max_tokens (Optional[int], optional): The maximum number of tokens to use. Defaults to None, which uses the default token limit.
            model (Optional[str], optional): The model to use. Defaults to None, which uses the default chat model.
            system_message (Optional[str], optional): The system message to use. Defaults to None, which uses the default system message.

        Returns:
            List[Any]: The truncated messages.
        """

        max_tokens = max_tokens or self.max_tokens
        model = model or self.chat_model
        system_message = (
            self.bot.default_system_message
            if system_message is None
            else system_message
        )

        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            # TODO: Handle this more gracefully
            encoding = tiktoken.encoding_for_model("gpt-4o")

        total_tokens = 0

        system_message_tokens = (
            0 if not system_message else (len(encoding.encode(system_message)) + 1)
        )

        if system_message_tokens > max_tokens:
            self.logger.log(
                f"System message is too long to fit within token limit ({system_message_tokens} tokens) - cannot proceed",
                "error",
            )
            return []

        total_tokens += system_message_tokens

        truncated_messages = []

        self.logger.log(f"Messages: {messages}", "debug")

        for message in [messages[0]] + list(reversed(messages[1:])):
            content = (
                message["content"]
                if isinstance(message["content"], str)
                else (
                    message["content"][0]["text"]
                    if isinstance(message["content"][0].get("text"), str)
                    else ""
                )
            )
            tokens = len(encoding.encode(content)) + 1
            if total_tokens + tokens > max_tokens:
                break
            total_tokens += tokens
            truncated_messages.append(message)

        system_message_dict = {
            "role": "system",
            "content": (
                system_message
                if isinstance(messages[0]["content"], str)
                else [{"type": "text", "text": system_message}]
            ),
        }

        return (
            system_message_dict
            + [truncated_messages[0]]
            + list(reversed(truncated_messages[1:]))
        )

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
                self.logger.log("Recursion depth exceeded, aborting.")
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

        if (
            allow_override
            and use_tools
            and self.tool_model
            and not (self._is_tool_model(chat_model) or self.force_tools)
        ):
            if self.tool_model:
                self.logger.log("Overriding chat model to use tools")
                chat_model = self.tool_model

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
            and self.emulate_tools
            and not self.force_tools
            and not self._is_tool_model(chat_model)
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
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }

        if (self._is_tool_model(chat_model) and use_tools) or self.force_tools:
            kwargs["tools"] = tools

        # TODO: Look into this
        if "gpt-4" in chat_model:
            kwargs["max_tokens"] = self.max_tokens

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
                    if tool_response is not False:
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
                self.logger.log("No more responses received, aborting.")
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
                            "Max tokens exceeded, falling back to no-tools response."
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
                    if tool_response is not False:
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
                    self.logger.log("No response received, aborting.")
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

        if not result_text:
            self.logger.log(
                "Received an empty response from the OpenAI endpoint.", "debug"
            )

        try:
            tokens_used = response.usage.total_tokens
        except Exception:
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
        except Exception:
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
        self.logger.log("Generating text from speech...")

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
        self.logger.log("Generating description for images in conversation...")

        system_message = "You are an image description generator. You generate descriptions for all images in the current conversation, one after another."

        messages = [{"role": "system", "content": system_message}] + messages[1:]

        chat_model = self.chat_model

        if not self._is_vision_model(chat_model):
            chat_model = self.vision_model or "gpt-4o"

        chat_partial = partial(
            self.openai_api.chat.completions.create,
            model=chat_model,
            messages=messages,
            user=str(user),
        )

        response = await self._request_with_retries(chat_partial)

        return response.choices[0].message.content, response.usage.total_tokens
