import markdown2
import tiktoken
import asyncio
import functools

from PIL import Image

from mautrix.client import Client
from mautrix.types import (
    RoomID,
    UserID,
    EventType,
    MessageType,
    MessageEvent,
    RoomDirectoryVisibility,
)
from mautrix.errors import (
    MForbidden,
    MNotFound,
    MUnknownToken,
    MForbidden,
    MatrixError,
)

from typing import Optional, List
from configparser import ConfigParser
from datetime import datetime
from io import BytesIO
from pathlib import Path
from contextlib import closing

import uuid
import traceback
import json
import importlib.util
import sys
import sqlite3

from .logging import Logger
from ..migrations import migrate
from ..callbacks import RESPONSE_CALLBACKS, EVENT_CALLBACKS
from ..commands import COMMANDS
from .openai import OpenAI
from .wolframalpha import WolframAlpha
from .trackingmore import TrackingMore


class GPTBot:
    # Default values
    database: Optional[sqlite3.Connection] = None
    crypto_store_path: Optional[str | Path] = None
    # Default name of rooms created by the bot
    display_name = default_room_name = "GPTBot"
    default_system_message: str = "You are a helpful assistant."
    # Force default system message to be included even if a custom room message is set
    force_system_message: bool = False
    max_tokens: int = 3000  # Maximum number of input tokens
    max_messages: int = 30  # Maximum number of messages to consider as input
    matrix_client: Optional[Client] = None
    sync_token: Optional[str] = None
    logger: Optional[Logger] = Logger()
    chat_api: Optional[OpenAI] = None
    image_api: Optional[OpenAI] = None
    classification_api: Optional[OpenAI] = None
    parcel_api: Optional[TrackingMore] = None
    operator: Optional[str] = None
    room_ignore_list: List[str] = []  # List of rooms to ignore invites from
    debug: bool = False
    logo: Optional[Image.Image] = None
    logo_uri: Optional[str] = None
    allowed_users: List[str] = []

    @classmethod
    def from_config(cls, config: ConfigParser):
        """Create a new GPTBot instance from a config file.

        Args:
            config (ConfigParser): ConfigParser instance with the bot's config.

        Returns:
            GPTBot: The new GPTBot instance.
        """

        # Create a new GPTBot instance
        bot = cls()

        # Set the database connection
        bot.database = (
            sqlite3.connect(config["Database"]["Path"])
            if "Database" in config and "Path" in config["Database"]
            else None
        )

        bot.crypto_store_path = (
            config["Database"]["CryptoStore"]
            if "Database" in config and "CryptoStore" in config["Database"]
            else None
        )

        # Override default values
        if "GPTBot" in config:
            bot.operator = config["GPTBot"].get("Operator", bot.operator)
            bot.default_room_name = config["GPTBot"].get(
                "DefaultRoomName", bot.default_room_name
            )
            bot.default_system_message = config["GPTBot"].get(
                "SystemMessage", bot.default_system_message
            )
            bot.force_system_message = config["GPTBot"].getboolean(
                "ForceSystemMessage", bot.force_system_message
            )
            bot.debug = config["GPTBot"].getboolean("Debug", bot.debug)

            if "LogLevel" in config["GPTBot"]:
                bot.logger = Logger(config["GPTBot"]["LogLevel"])

            logo_path = config["GPTBot"].get(
                "Logo", str(Path(__file__).parent.parent / "assets/logo.png")
            )

            bot.logger.log(f"Loading logo from {logo_path}", "debug")

            if Path(logo_path).exists() and Path(logo_path).is_file():
                bot.logo = Image.open(logo_path)

            bot.display_name = config["GPTBot"].get("DisplayName", bot.display_name)

            if "AllowedUsers" in config["GPTBot"]:
                bot.allowed_users = json.loads(config["GPTBot"]["AllowedUsers"])

        bot.chat_api = bot.image_api = bot.classification_api = OpenAI(
            config["OpenAI"]["APIKey"], config["OpenAI"].get("Model"), bot.logger
        )
        bot.max_tokens = config["OpenAI"].getint("MaxTokens", bot.max_tokens)
        bot.max_messages = config["OpenAI"].getint("MaxMessages", bot.max_messages)

        if "BaseURL" in config["OpenAI"]:
            bot.chat_api.base_url = config["OpenAI"]["BaseURL"]
            bot.image_api = None

        # Set up WolframAlpha
        if "WolframAlpha" in config:
            bot.calculation_api = WolframAlpha(
                config["WolframAlpha"]["APIKey"], bot.logger
            )

        # Set up TrackingMore
        if "TrackingMore" in config:
            bot.parcel_api = TrackingMore(config["TrackingMore"]["APIKey"], bot.logger)

        # Set up the Matrix client

        assert "Matrix" in config, "Matrix config not found"

        bot.homeserver = config["Matrix"]["Homeserver"]
        bot.access_token = config["Matrix"]["AccessToken"]
        bot.user_id = config["Matrix"].get("UserID")
        bot.device_id = config["Matrix"].get("DeviceID")

        return bot

    async def _get_user_id(self) -> str:
        """Get the user ID of the bot from the whoami endpoint.
        Requires an access token to be set up.

        Returns:
            str: The user ID of the bot.
        """

        pass
        # TODO: Implement

    async def _last_n_messages(self, room: str | RoomID, n: Optional[int]):
        pass
        # TODO: Implement

    def _truncate(
        self,
        messages: list,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
    ):
        max_tokens = max_tokens or self.max_tokens
        model = model or self.chat_api.chat_model
        system_message = (
            self.default_system_message if system_message is None else system_message
        )

        encoding = tiktoken.encoding_for_model(model)
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

        total_tokens = len(system_message) + 1
        truncated_messages = []

        for message in [messages[0]] + list(reversed(messages[1:])):
            content = message["content"]
            tokens = len(encoding.encode(content)) + 1
            if total_tokens + tokens > max_tokens:
                break
            total_tokens += tokens
            truncated_messages.append(message)

        return [truncated_messages[0]] + list(reversed(truncated_messages[1:]))

    async def _get_device_id(self) -> str:
        """Guess the device ID of the bot.
        Requires an access token to be set up.

        Returns:
            str: The guessed device ID.
        """

        assert self.matrix_client, "Matrix client not set up"

        device_id = self.matrix_client.device_id

        if not device_id:
            assert self.matrix_client.access_token, "Access token not set up"

            # TODO: Implement

        return device_id

    async def process_command(self, room: RoomID, event: MessageEvent):
        """Process a command. Called from the event_callback() method.
        Delegates to the appropriate command handler.

        Args:
            room (RoomID): The room the command was sent in.
            event (MessageEvent): The event containing the command.
        """

        self.logger.log(
            f"Received command {event.body} from {event.sender} in room {room.room_id}",
            "debug",
        )
        command = event.body.split()[1] if event.body.split()[1:] else None

        await COMMANDS.get(command, COMMANDS[None])(room, event, self)

    def room_uses_classification(self, room: RoomID | str) -> bool:
        """Check if a room uses classification.

        Args:
            room (RoomID | str): The room to check.

        Returns:
            bool: Whether the room uses classification.
        """
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "use_classification"),
            )
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    async def _event_callback(self, room: RoomID, event: MessageEvent):
        self.logger.log("Received event: " + str(event.event_id), "debug")
        try:
            for eventtype, callback in EVENT_CALLBACKS.items():
                if isinstance(event, eventtype):
                    await callback(room, event, self)
        except Exception as e:
            self.logger.log(
                f"Error in event callback for {event.__class__}: {e}", "error"
            )

            if self.debug:
                await self.send_message(
                    room, f"Error: {e}\n\n```\n{traceback.format_exc()}\n```", True
                )

    def user_is_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to use the bot.

        Args:
            user_id (str): The user ID to check.

        Returns:
            bool: Whether the user is allowed to use the bot.
        """

        return (
            (
                user_id in self.allowed_users
                or f"*:{user_id.split(':')[1]}" in self.allowed_users
                or f"@*:{user_id.split(':')[1]}" in self.allowed_users
            )
            if self.allowed_users
            else True
        )

    async def event_callback(self, room: RoomID, event: MessageEvent):
        """Callback for events.

        Args:
            room (RoomID): The room the event was sent in.
            event (MessageEvent): The event.
        """

        if event.sender == self.matrix_client.user_id:
            return

        if not self.user_is_allowed(event.sender):
            if len(room.users) == 2:
                await self.matrix_client.room_send(
                    room.room_id,
                    "m.room.message",
                    {
                        "msgtype": "m.notice",
                        "body": f"You are not allowed to use this bot. Please contact {self.operator} for more information.",
                    },
                )
            return

        task = asyncio.create_task(self._event_callback(room, event))

    def room_uses_timing(self, room: RoomID):
        """Check if a room uses timing.

        Args:
            room (RoomID): The room to check.

        Returns:
            bool: Whether the room uses timing.
        """
        room_id = room.room_id

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "use_timing"),
            )
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    async def accept_pending_invites(self):
        """Accept all pending invites."""

        assert self.matrix_client, "Matrix client not set up"

        invites = self.matrix_client.invited_rooms

        for invite in invites.keys():
            if invite in self.room_ignore_list:
                self.logger.log(
                    f"Ignoring invite to room {invite} (room is in ignore list)",
                    "debug",
                )
                continue

            self.logger.log(f"Accepting invite to room {invite}")

            response = await self.matrix_client.join(invite)

            if isinstance(response, JoinError):
                self.logger.log(
                    f"Error joining room {invite}: {response.message}. Not trying again.",
                    "error",
                )

                leave_response = await self.matrix_client.room_leave(invite)

                if isinstance(leave_response, RoomLeaveError):
                    self.logger.log(
                        f"Error leaving room {invite}: {leave_response.message}",
                        "error",
                    )
                    self.room_ignore_list.append(invite)

    async def upload_file(
        self,
        file: bytes,
        filename: str = "file",
        mime: str = "application/octet-stream",
    ) -> str:
        """Upload a file to the homeserver.

        Args:
            file (bytes): The file to upload.
            filename (str, optional): The name of the file. Defaults to "file".
            mime (str, optional): The MIME type of the file. Defaults to "application/octet-stream".

        Returns:
            str: The MXC URI of the uploaded file.
        """

        bio = BytesIO(file)
        bio.seek(0)

        response, _ = await self.matrix_client.upload(
            bio, content_type=mime, filename=filename, filesize=len(file)
        )

        return response.content_uri

    async def send_image(
        self, room: RoomID, image: bytes, message: Optional[str] = None
    ):
        """Send an image to a room.

        Args:
            room (RoomID): The room to send the image to.
            image (bytes): The image to send.
            message (str, optional): The message to send with the image. Defaults to None.
        """

        self.logger.log(
            f"Sending image of size {len(image)} bytes to room {room.room_id}", "debug"
        )

        bio = BytesIO(image)
        img = Image.open(bio)
        mime = Image.MIME[img.format]

        (width, height) = img.size

        self.logger.log(
            f"Uploading - Image size: {width}x{height} pixels, MIME type: {mime}",
            "debug",
        )

        content_uri = await self.upload_file(image, "image", mime)

        self.logger.log("Uploaded image - sending message...", "debug")

        content = {
            "body": message or "",
            "info": {
                "mimetype": mime,
                "size": len(image),
                "w": width,
                "h": height,
            },
            "msgtype": "m.image",
            "url": content_uri,
        }

        status = await self.matrix_client.room_send(
            room.room_id, "m.room.message", content
        )

        self.logger.log("Sent image", "debug")

    async def handle_event(self, event):
        """Handle an event."""

        for event_type, callback in EVENT_CALLBACKS.items():
            if isinstance(event, event_type):
                print(event_type, callback)
                await callback(event, self)

    async def send_message(
        self, room: RoomID | str, message: str, notice: bool = False
    ):
        """Send a message to a room.

        Args:
            room (RoomID): The room to send the message to.
            message (str): The message to send.
            notice (bool): Whether to send the message as a notice. Defaults to False.
        """

        if isinstance(room, str):
            room = self.matrix_client.rooms[room]

        markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
        formatted_body = markdowner.convert(message)

        msgtype = "m.notice" if notice else "m.text"

        msgcontent = {
            "msgtype": msgtype,
            "body": message,
            "format": "org.matrix.custom.html",
            "formatted_body": formatted_body,
        }

        content = None

        if self.matrix_client.olm and room.encrypted:
            try:
                if not room.members_synced:
                    responses = []
                    responses.append(
                        await self.matrix_client.joined_members(room.room_id)
                    )

                if self.matrix_client.olm.should_share_group_session(room.room_id):
                    try:
                        event = self.matrix_client.sharing_session[room.room_id]
                        await event.wait()
                    except KeyError:
                        await self.matrix_client.share_group_session(
                            room.room_id,
                            ignore_unverified_devices=True,
                        )

                if msgtype != "m.reaction":
                    response = self.matrix_client.encrypt(
                        room.room_id, "m.room.message", msgcontent
                    )
                    msgtype, content = response

            except Exception as e:
                self.logger.log(
                    f"Error encrypting message: {e} - sending unencrypted", "warning"
                )
                raise

        if not content:
            msgtype = "m.room.message"
            content = msgcontent

        method, path, data = Api.room_send(
            self.matrix_client.access_token,
            room.room_id,
            msgtype,
            content,
            uuid.uuid4(),
        )

        response = await self.matrix_client._send(
            RoomSendResponse, method, path, data, (room.room_id,)
        )

        if isinstance(response, RoomSendError):
            self.logger.log(f"Error sending message: {response.message}", "error")
            return

    def log_api_usage(
        self, message: MessageEvent | str, room: RoomID | str, api: str, tokens: int
    ):
        """Log API usage to the database.

        Args:
            message (MessageEvent): The event that triggered the API usage.
            room (RoomID | str): The room the event was sent in.
            api (str): The API that was used.
            tokens (int): The number of tokens used.
        """

        if not self.database:
            return

        if isinstance(message, Event):
            message = message.event_id

        if isinstance(room, MatrixRoom):
            room = room.room_id

        self.database.execute(
            "INSERT INTO token_usage (message_id, room_id, tokens, api, timestamp) VALUES (?, ?, ?, ?, ?)",
            (message, room, tokens, api, datetime.now()),
        )

    async def run(self):
        """Start the bot."""

        # Set up the Matrix client

        self.matrix_client: Client = self.matrix_client or Client(base_url=self.homeserver, token=self.access_token)

        iam = await self.matrix_client.whoami()

        self.logger.log(f"Logged in as {iam.user_id} (device ID: {iam.device_id})", "info")

        # Set up database

        IN_MEMORY = False
        if not self.database:
            self.logger.log(
                "No database connection set up, using in-memory database. Data will be lost on bot shutdown.",
                "warning",
            )
            IN_MEMORY = True
            self.database = sqlite3.connect(":memory:")

        self.logger.log("Running migrations...")

        try:
            before, after = migrate(self.database)
        except sqlite3.DatabaseError as e:
            self.logger.log(f"Error migrating database: {e}", "critical")

            self.logger.log(
                "If you have just updated the bot, the previous version of the database may be incompatible with this version. Please delete the database file and try again.",
                "critical",
            )
            exit(1)

        if before != after:
            self.logger.log(f"Migrated from version {before} to {after}.")
        else:
            self.logger.log(f"Already at latest version {after}.")

        # Set up event handlers
        self.matrix_client.add_event_handler(EventType.ALL, self.handle_event)

        # Run initial sync (now includes joining rooms)
        sync = await self.matrix_client.sync(timeout=30000)


        # Set custom name / logo

        # TODO: Implement

        # Start syncing events
        self.logger.log("Starting sync loop...", "warning")
        try:
            await self.matrix_client.start(None)
        finally:
            self.logger.log("Syncing one last time...", "warning")
            await self.matrix_client.sync(timeout=30000)

    async def create_space(
        self, name, visibility=RoomDirectoryVisibility.PRIVATE
    ) -> str:
        """Create a space.

        Args:
            name (str): The name of the space.
            visibility (RoomDirectoryVisibility, optional): The visibility of the space. Defaults to RoomVisibility.private.

        Returns:
            MatrixRoom: The created space.
        """

        response = await self.matrix_client.room_create(
            name=name, visibility=visibility, space=True
        )

        if isinstance(response, RoomCreateError):
            self.logger.log(f"Error creating space: {response.message}", "error")
            return

        return response.room_id

    async def add_rooms_to_space(
        self, space: RoomID | str, rooms: List[RoomID | str]
    ):
        """Add rooms to a space.

        Args:
            space (RoomID | str): The space to add the rooms to.
            rooms (List[RoomID | str]): The rooms to add to the space.
        """

        if isinstance(space, MatrixRoom):
            space = space.room_id

        for room in rooms:
            if isinstance(room, MatrixRoom):
                room = room.room_id

            if space == room:
                self.logger.log(f"Refusing to add {room} to itself", "warning")
                continue

            self.logger.log(f"Adding {room} to {space}...", "debug")

            await self.matrix_client.room_put_state(
                space,
                "m.space.child",
                {
                    "via": [room.split(":")[1], space.split(":")[1]],
                },
                room,
            )

            await self.matrix_client.room_put_state(
                room,
                "m.room.parent",
                {"via": [space.split(":")[1], room.split(":")[1]], "canonical": True},
                space,
            )

    def respond_to_room_messages(self, room: RoomID | str) -> bool:
        """Check whether the bot should respond to all messages sent in a room.

        Args:
            room (RoomID | str): The room to check.

        Returns:
            bool: Whether the bot should respond to all messages sent in the room.
        """

        if isinstance(room, RoomID):
            room = room.room_id

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room, "always_reply"),
            )
            result = cursor.fetchone()

        return True if not result else bool(int(result[0]))

    async def process_query(
        self, room: RoomID, event: MessageEvent, from_chat_command: bool = False
    ):
        """Process a query message. Generates a response and sends it to the room.

        Args:
            room (RoomID): The room the message was sent in.
            event (MessageEvent): The event that triggered the query.
            from_chat_command (bool, optional): Whether the query was sent via the `!gptbot chat` command. Defaults to False.
        """

        if not (
            from_chat_command
            or self.respond_to_room_messages(room)
            or self.matrix_client.whoami().user_id in event.body
        ):
            return

        # TODO: await self.matrix_client.room_typing(room.room_id, True)

        # TODO: await self.matrix_client.room_read_markers(room.room_id, event.event_id)

        if (not from_chat_command) and self.room_uses_classification(room):
            try:
                classification, tokens = await self.classification_api.classify_message(
                    event.body, room.room_id
                )
            except Exception as e:
                self.logger.log(f"Error classifying message: {e}", "error")
                await self.send_message(
                    room, "Something went wrong. Please try again.", True
                )
                return

            self.log_api_usage(
                event,
                room,
                f"{self.classification_api.api_code}-{self.classification_api.classification_api}",
                tokens,
            )

            if not classification["type"] == "chat":
                event.body = (
                    f"!gptbot {classification['type']} {classification['prompt']}"
                )
                await self.process_command(room, event)
                return

        try:
            last_messages = await self._last_n_messages(room.room_id, 20)
        except Exception as e:
            self.logger.log(f"Error getting last messages: {e}", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True
            )
            return

        system_message = self.get_system_message(room)

        chat_messages = [{"role": "system", "content": system_message}]

        for message in last_messages:
            role = (
                "assistant" if message.sender == self.matrix_client.user_id else "user"
            )
            if not message.event_id == event.event_id:
                chat_messages.append({"role": role, "content": message.body})

        chat_messages.append({"role": "user", "content": event.body})

        # Truncate messages to fit within the token limit
        truncated_messages = self._truncate(
            chat_messages, self.max_tokens - 1, system_message=system_message
        )

        try:
            response, tokens_used = await self.chat_api.generate_chat_response(
                chat_messages, user=room.room_id
            )
        except Exception as e:
            self.logger.log(f"Error generating response: {e}", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True
            )
            return

        if response:
            self.log_api_usage(
                event,
                room,
                f"{self.chat_api.api_code}-{self.chat_api.chat_api}",
                tokens_used,
            )

            self.logger.log(f"Sending response to room {room.room_id}...")

            # Convert markdown to HTML

            message = await self.send_message(room, response)

        else:
            # Send a notice to the room if there was an error
            self.logger.log("Didn't get a response from GPT API", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True
            )

        await self.matrix_client.room_typing(room.room_id, False)

    def get_system_message(self, room: RoomID | str) -> str:
        """Get the system message for a room.

        Args:
            room (RoomID | str): The room to get the system message for.

        Returns:
            str: The system message.
        """

        default = self.default_system_message

        if isinstance(room, str):
            room_id = room
        else:
            room_id = room.room_id

        with closing(self.database.cursor()) as cur:
            cur.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "system_message"),
            )
            system_message = cur.fetchone()

        complete = (
            (default if ((not system_message) or self.force_system_message) else "")
            + ("\n\n" + system_message[0] if system_message else "")
        ).strip()

        return complete

    def __del__(self):
        """Close the bot."""

        if self.matrix_client:
            asyncio.run(self.matrix_client.close())

        if self.database:
            self.database.close()
