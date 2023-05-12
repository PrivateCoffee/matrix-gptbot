import markdown2
import duckdb
import tiktoken
import magic
import asyncio

from PIL import Image

from nio import (
    AsyncClient,
    AsyncClientConfig,
    WhoamiResponse,
    DevicesResponse,
    Event,
    Response,
    MatrixRoom,
    Api,
    RoomMessagesError,
    MegolmEvent,
    GroupEncryptionError,
    EncryptionError,
    RoomMessageText,
    RoomSendResponse,
    SyncResponse,
    RoomMessageNotice,
    JoinError,
    RoomLeaveError,
    RoomSendError,
    RoomVisibility,
    RoomCreateResponse,
    RoomCreateError,
)
from nio.crypto import Olm

from typing import Optional, List, Dict, Tuple
from configparser import ConfigParser
from datetime import datetime
from io import BytesIO
from pathlib import Path

import uuid
import traceback
import json

from .logging import Logger
from migrations import migrate
from callbacks import RESPONSE_CALLBACKS, EVENT_CALLBACKS
from commands import COMMANDS
from .store import DuckDBStore
from .openai import OpenAI
from .wolframalpha import WolframAlpha
from .trackingmore import TrackingMore


class GPTBot:
    # Default values
    database: Optional[duckdb.DuckDBPyConnection] = None
    # Default name of rooms created by the bot
    display_name = default_room_name = "GPTBot"
    default_system_message: str = "You are a helpful assistant."
    # Force default system message to be included even if a custom room message is set
    force_system_message: bool = False
    max_tokens: int = 3000  # Maximum number of input tokens
    max_messages: int = 30  # Maximum number of messages to consider as input
    matrix_client: Optional[AsyncClient] = None
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
        bot.database = duckdb.connect(
            config["Database"]["Path"]) if "Database" in config and "Path" in config["Database"] else None

        # Override default values
        if "GPTBot" in config:
            bot.operator = config["GPTBot"].get("Operator", bot.operator)
            bot.default_room_name = config["GPTBot"].get(
                "DefaultRoomName", bot.default_room_name)
            bot.default_system_message = config["GPTBot"].get(
                "SystemMessage", bot.default_system_message)
            bot.force_system_message = config["GPTBot"].getboolean(
                "ForceSystemMessage", bot.force_system_message)
            bot.debug = config["GPTBot"].getboolean("Debug", bot.debug)

            logo_path = config["GPTBot"].get("Logo", str(
                Path(__file__).parent.parent / "assets/logo.png"))

            bot.logger.log(f"Loading logo from {logo_path}")

            if Path(logo_path).exists() and Path(logo_path).is_file():
                bot.logo = Image.open(logo_path)

            bot.display_name = config["GPTBot"].get(
                "DisplayName", bot.display_name)

            if "AllowedUsers" in config["GPTBot"]:
                bot.allowed_users = json.loads(config["GPTBot"]["AllowedUsers"])

        bot.chat_api = bot.image_api = bot.classification_api = OpenAI(
            config["OpenAI"]["APIKey"], config["OpenAI"].get("Model"), bot.logger)
        bot.max_tokens = config["OpenAI"].getint("MaxTokens", bot.max_tokens)
        bot.max_messages = config["OpenAI"].getint(
            "MaxMessages", bot.max_messages)

        # Set up WolframAlpha
        if "WolframAlpha" in config:
            bot.calculation_api = WolframAlpha(
                config["WolframAlpha"]["APIKey"], bot.logger)

        # Set up TrackingMore
        if "TrackingMore" in config:
            bot.parcel_api = TrackingMore(
                config["TrackingMore"]["APIKey"], bot.logger)

        # Set up the Matrix client

        assert "Matrix" in config, "Matrix config not found"

        homeserver = config["Matrix"]["Homeserver"]
        bot.matrix_client = AsyncClient(homeserver)
        bot.matrix_client.access_token = config["Matrix"]["AccessToken"]
        bot.matrix_client.user_id = config["Matrix"].get("UserID")
        bot.matrix_client.device_id = config["Matrix"].get("DeviceID")

        # Return the new GPTBot instance
        return bot

    async def _get_user_id(self) -> str:
        """Get the user ID of the bot from the whoami endpoint.
        Requires an access token to be set up.

        Returns:
            str: The user ID of the bot.
        """

        assert self.matrix_client, "Matrix client not set up"

        user_id = self.matrix_client.user_id

        if not user_id:
            assert self.matrix_client.access_token, "Access token not set up"

            response = await self.matrix_client.whoami()

            if isinstance(response, WhoamiResponse):
                user_id = response.user_id
            else:
                raise Exception(f"Could not get user ID: {response}")

        return user_id

    async def _last_n_messages(self, room: str | MatrixRoom, n: Optional[int]):
        messages = []
        n = n or bot.max_messages
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        self.logger.log(
            f"Fetching last {2*n} messages from room {room_id} (starting at {self.sync_token})...")

        response = await self.matrix_client.room_messages(
            room_id=room_id,
            start=self.sync_token,
            limit=2*n,
        )

        if isinstance(response, RoomMessagesError):
            raise Exception(
                f"Error fetching messages: {response.message} (status code {response.status_code})", "error")

        for event in response.chunk:
            if len(messages) >= n:
                break
            if isinstance(event, MegolmEvent):
                try:
                    event = await self.matrix_client.decrypt_event(event)
                except (GroupEncryptionError, EncryptionError):
                    self.logger.log(
                        f"Could not decrypt message {event.event_id} in room {room_id}", "error")
                    continue
            if isinstance(event, (RoomMessageText, RoomMessageNotice)):
                if event.body.startswith("!gptbot ignoreolder"):
                    break
                if (not event.body.startswith("!")) or (event.body.startswith("!gptbot")):
                    messages.append(event)

        self.logger.log(f"Found {len(messages)} messages (limit: {n})")

        # Reverse the list so that messages are in chronological order
        return messages[::-1]

    def _truncate(self, messages: list, max_tokens: Optional[int] = None,
                  model: Optional[str] = None, system_message: Optional[str] = None):
        max_tokens = max_tokens or self.max_tokens
        model = model or self.chat_api.chat_model
        system_message = self.default_system_message if system_message is None else system_message

        encoding = tiktoken.encoding_for_model(model)
        total_tokens = 0

        system_message_tokens = 0 if not system_message else (
            len(encoding.encode(system_message)) + 1)

        if system_message_tokens > max_tokens:
            self.logger.log(
                f"System message is too long to fit within token limit ({system_message_tokens} tokens) - cannot proceed", "error")
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

            devices = await self.matrix_client.devices()

            if isinstance(devices, DevicesResponse):
                device_id = devices.devices[0].id

        return device_id

    async def process_command(self, room: MatrixRoom, event: RoomMessageText):
        """Process a command. Called from the event_callback() method.
        Delegates to the appropriate command handler.

        Args:
            room (MatrixRoom): The room the command was sent in.
            event (RoomMessageText): The event containing the command.
        """

        self.logger.log(
            f"Received command {event.body} from {event.sender} in room {room.room_id}")
        command = event.body.split()[1] if event.body.split()[1:] else None

        await COMMANDS.get(command, COMMANDS[None])(room, event, self)

    def room_uses_classification(self, room: MatrixRoom | str) -> bool:
        """Check if a room uses classification.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            bool: Whether the room uses classification.
        """
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?", (room_id, "use_classification"))
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    async def _event_callback(self, room: MatrixRoom, event: Event):
        self.logger.log("Received event: " + str(event.event_id), "debug")
        try:
            for eventtype, callback in EVENT_CALLBACKS.items():
                if isinstance(event, eventtype):
                    await callback(room, event, self)
        except Exception as e:
            self.logger.log(
                f"Error in event callback for {event.__class__}: {e}", "error")

            if self.debug:
                await self.send_message(room, f"Error: {e}\n\n```\n{traceback.format_exc()}\n```", True)

    def user_is_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to use the bot.

        Args:
            user_id (str): The user ID to check.

        Returns:
            bool: Whether the user is allowed to use the bot.
        """

        return (
            user_id in self.allowed_users or 
            f"*:{user_id.split(':')[1]}" in self.allowed_users or
            f"@*:{user_id.split(':')[1]}" in self.allowed_users
        ) if self.allowed_users else True

    async def event_callback(self, room: MatrixRoom, event: Event):
        """Callback for events.

        Args:
            room (MatrixRoom): The room the event was sent in.
            event (Event): The event.
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
                        "body": f"You are not allowed to use this bot. Please contact {self.operator} for more information."
                    }
                )
            return

        task = asyncio.create_task(self._event_callback(room, event))

    def room_uses_timing(self, room: MatrixRoom):
        """Check if a room uses timing.

        Args:
            room (MatrixRoom): The room to check.

        Returns:
            bool: Whether the room uses timing.
        """
        room_id = room.room_id

        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?", (room_id, "use_timing"))
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    async def _response_callback(self, response: Response):
        for response_type, callback in RESPONSE_CALLBACKS.items():
            if isinstance(response, response_type):
                await callback(response, self)

    async def response_callback(self, response: Response):
        task = asyncio.create_task(self._response_callback(response))

    async def accept_pending_invites(self):
        """Accept all pending invites."""

        assert self.matrix_client, "Matrix client not set up"

        invites = self.matrix_client.invited_rooms

        for invite in invites.keys():
            if invite in self.room_ignore_list:
                self.logger.log(
                    f"Ignoring invite to room {invite} (room is in ignore list)")
                continue

            self.logger.log(f"Accepting invite to room {invite}")

            response = await self.matrix_client.join(invite)

            if isinstance(response, JoinError):
                self.logger.log(
                    f"Error joining room {invite}: {response.message}. Not trying again.", "error")

                leave_response = await self.matrix_client.room_leave(invite)

                if isinstance(leave_response, RoomLeaveError):
                    self.logger.log(
                        f"Error leaving room {invite}: {leave_response.message}", "error")
                    self.room_ignore_list.append(invite)

    async def upload_file(self, file: bytes, filename: str = "file", mime: str = "application/octet-stream") -> str:
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
            bio,
            content_type=mime,
            filename=filename,
            filesize=len(file)
        )

        return response.content_uri

    async def send_image(self, room: MatrixRoom, image: bytes, message: Optional[str] = None):
        """Send an image to a room.

        Args:
            room (MatrixRoom): The room to send the image to.
            image (bytes): The image to send.
            message (str, optional): The message to send with the image. Defaults to None.
        """

        self.logger.log(
            f"Sending image of size {len(image)} bytes to room {room.room_id}")

        bio = BytesIO(image)
        img = Image.open(bio)
        mime = Image.MIME[img.format]

        (width, height) = img.size

        self.logger.log(
            f"Uploading - Image size: {width}x{height} pixels, MIME type: {mime}")

        content_uri = await self.upload_file(image, "image", mime)

        self.logger.log("Uploaded image - sending message...")

        content = {
            "body": message or "",
            "info": {
                "mimetype": mime,
                "size": len(image),
                "w": width,
                "h": height,
            },
            "msgtype": "m.image",
            "url": content_uri
        }

        status = await self.matrix_client.room_send(
            room.room_id,
            "m.room.message",
            content
        )

        self.logger.log(str(status), "debug")

        self.logger.log("Sent image")

    async def send_message(self, room: MatrixRoom | str, message: str, notice: bool = False):
        """Send a message to a room.

        Args:
            room (MatrixRoom): The room to send the message to.
            message (str): The message to send.
            notice (bool): Whether to send the message as a notice. Defaults to False.
        """

        if isinstance(room, str):
            room = self.matrix_client.rooms[room]

        markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
        formatted_body = markdowner.convert(message)

        msgtype = "m.notice" if notice else "m.text"

        msgcontent = {"msgtype": msgtype, "body": message,
                      "format": "org.matrix.custom.html", "formatted_body": formatted_body}

        content = None

        if self.matrix_client.olm and room.encrypted:
            try:
                if not room.members_synced:
                    responses = []
                    responses.append(await self.matrix_client.joined_members(room.room_id))

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
                        room.room_id, "m.room.message", msgcontent)
                    msgtype, content = response

            except Exception as e:
                self.logger.log(
                    f"Error encrypting message: {e} - sending unencrypted", "error")
                raise

        if not content:
            msgtype = "m.room.message"
            content = msgcontent

        method, path, data = Api.room_send(
            self.matrix_client.access_token, room.room_id, msgtype, content, uuid.uuid4()
        )

        response = await self.matrix_client._send(RoomSendResponse, method, path, data, (room.room_id,))

        if isinstance(response, RoomSendError):
            self.logger.log(
                f"Error sending message: {response.message}", "error")
            return

    def log_api_usage(self, message: Event | str, room: MatrixRoom | str, api: str, tokens: int):
        """Log API usage to the database.

        Args:
            message (Event): The event that triggered the API usage.
            room (MatrixRoom | str): The room the event was sent in.
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
            (message, room, tokens, api, datetime.now())
        )

    async def run(self):
        """Start the bot."""

        # Set up the Matrix client

        assert self.matrix_client, "Matrix client not set up"
        assert self.matrix_client.access_token, "Access token not set up"

        if not self.matrix_client.user_id:
            self.matrix_client.user_id = await self._get_user_id()

        if not self.matrix_client.device_id:
            self.matrix_client.device_id = await self._get_device_id()

        # Set up database

        IN_MEMORY = False
        if not self.database:
            self.logger.log(
                "No database connection set up, using in-memory database. Data will be lost on bot shutdown.")
            IN_MEMORY = True
            self.database = DuckDBPyConnection(":memory:")

        self.logger.log("Running migrations...")
        before, after = migrate(self.database)
        if before != after:
            self.logger.log(f"Migrated from version {before} to {after}.")
        else:
            self.logger.log(f"Already at latest version {after}.")

        if IN_MEMORY:
            client_config = AsyncClientConfig(
                store_sync_tokens=True, encryption_enabled=False)
        else:
            matrix_store = DuckDBStore
            client_config = AsyncClientConfig(
                store_sync_tokens=True, encryption_enabled=True, store=matrix_store)
            self.matrix_client.config = client_config
            self.matrix_client.store = matrix_store(
                self.matrix_client.user_id,
                self.matrix_client.device_id,
                self.database
            )

            self.matrix_client.olm = Olm(
                self.matrix_client.user_id,
                self.matrix_client.device_id,
                self.matrix_client.store
            )

            self.matrix_client.encrypted_rooms = self.matrix_client.store.load_encrypted_rooms()

        # Run initial sync (now includes joining rooms)
        sync = await self.matrix_client.sync(timeout=30000)
        if isinstance(sync, SyncResponse):
            await self.response_callback(sync)
        else:
            self.logger.log(f"Initial sync failed, aborting: {sync}", "error")
            return

        # Set up callbacks

        self.matrix_client.add_event_callback(self.event_callback, Event)
        self.matrix_client.add_response_callback(
            self.response_callback, Response)

        # Set custom name / logo

        if self.display_name:
            self.logger.log(f"Setting display name to {self.display_name}")
            await self.matrix_client.set_displayname(self.display_name)
        if self.logo:
            self.logger.log("Setting avatar...")
            logo_bio = BytesIO()
            self.logo.save(logo_bio, format=self.logo.format)
            uri = await self.upload_file(logo_bio.getvalue(), "logo", Image.MIME[self.logo.format])
            self.logo_uri = uri

            asyncio.create_task(self.matrix_client.set_avatar(uri))

            for room in self.matrix_client.rooms.keys():
                self.logger.log(f"Setting avatar for {room}...", "debug")
                asyncio.create_task(self.matrix_client.room_put_state(room, "m.room.avatar", {
                    "url": uri
                }, ""))

        # Start syncing events
        self.logger.log("Starting sync loop...")
        try:
            await self.matrix_client.sync_forever(timeout=30000)
        finally:
            self.logger.log("Syncing one last time...")
            await self.matrix_client.sync(timeout=30000)

    async def create_space(self, name, visibility=RoomVisibility.private) -> str:
        """Create a space.

        Args:
            name (str): The name of the space.
            visibility (RoomVisibility, optional): The visibility of the space. Defaults to RoomVisibility.private.

        Returns:
            MatrixRoom: The created space.
        """

        response = await self.matrix_client.room_create(
            name=name, visibility=visibility, space=True)

        if isinstance(response, RoomCreateError):
            self.logger.log(
                f"Error creating space: {response.message}", "error")
            return

        return response.room_id

    async def add_rooms_to_space(self, space: MatrixRoom | str, rooms: List[MatrixRoom | str]):
        """Add rooms to a space.

        Args:
            space (MatrixRoom | str): The space to add the rooms to.
            rooms (List[MatrixRoom | str]): The rooms to add to the space.
        """

        if isinstance(space, MatrixRoom):
            space = space.room_id

        for room in rooms:
            if isinstance(room, MatrixRoom):
                room = room.room_id

            if space == room:
                self.logger.log(
                    f"Refusing to add {room} to itself", "warning")
                continue

            self.logger.log(f"Adding {room} to {space}...")

            await self.matrix_client.room_put_state(space, "m.space.child", {
                "via": [room.split(":")[1], space.split(":")[1]],
            }, room)

            await self.matrix_client.room_put_state(room, "m.room.parent", {
                "via": [space.split(":")[1], room.split(":")[1]],
                "canonical": True
            }, space)

    def respond_to_room_messages(self, room: MatrixRoom | str) -> bool:
        """Check whether the bot should respond to all messages sent in a room.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            bool: Whether the bot should respond to all messages sent in the room.
        """

        if isinstance(room, MatrixRoom):
            room = room.room_id

        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?", (room, "always_reply"))
            result = cursor.fetchone()

        return True if not result else bool(int(result[0]))

    async def process_query(self, room: MatrixRoom, event: RoomMessageText, from_chat_command: bool = False):
        """Process a query message. Generates a response and sends it to the room.

        Args:
            room (MatrixRoom): The room the message was sent in.
            event (RoomMessageText): The event that triggered the query.
            from_chat_command (bool, optional): Whether the query was sent via the `!gptbot chat` command. Defaults to False.
        """

        if not (from_chat_command or self.respond_to_room_messages(room) or self.matrix_client.user_id in event.body):
            return

        await self.matrix_client.room_typing(room.room_id, True)

        await self.matrix_client.room_read_markers(room.room_id, event.event_id)

        if (not from_chat_command) and self.room_uses_classification(room):
            classification, tokens = self.classification_api.classify_message(
                event.body, room.room_id)

            self.log_api_usage(
                event, room, f"{self.classification_api.api_code}-{self.classification_api.classification_api}", tokens)

            if not classification["type"] == "chat":
                event.body = f"!gptbot {classification['type']} {classification['prompt']}"
                await self.process_command(room, event)
                return

        try:
            last_messages = await self._last_n_messages(room.room_id, 20)
        except Exception as e:
            self.logger.log(f"Error getting last messages: {e}", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True)
            return

        system_message = self.get_system_message(room)

        chat_messages = [{"role": "system", "content": system_message}]

        for message in last_messages:
            role = "assistant" if message.sender == self.matrix_client.user_id else "user"
            if not message.event_id == event.event_id:
                chat_messages.append({"role": role, "content": message.body})

        chat_messages.append({"role": "user", "content": event.body})

        # Truncate messages to fit within the token limit
        truncated_messages = self._truncate(
            chat_messages, self.max_tokens - 1, system_message=system_message)

        try:
            response, tokens_used = self.chat_api.generate_chat_response(
                chat_messages, user=room.room_id)
        except Exception as e:
            self.logger.log(f"Error generating response: {e}", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True)
            return

        if response:
            self.log_api_usage(
                event, room, f"{self.chat_api.api_code}-{self.chat_api.chat_api}", tokens_used)

            self.logger.log(f"Sending response to room {room.room_id}...")

            # Convert markdown to HTML

            message = await self.send_message(room, response)

        else:
            # Send a notice to the room if there was an error
            self.logger.log("Didn't get a response from GPT API", "error")
            await send_message(
                room, "Something went wrong. Please try again.", True)

        await self.matrix_client.room_typing(room.room_id, False)

    def get_system_message(self, room: MatrixRoom | str) -> str:
        """Get the system message for a room.

        Args:
            room (MatrixRoom | str): The room to get the system message for.

        Returns:
            str: The system message.
        """

        default = self.default_system_message

        if isinstance(room, str):
            room_id = room
        else:
            room_id = room.room_id

        with self.database.cursor() as cur:
            cur.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "system_message")
            )
            system_message = cur.fetchone()

        complete = ((default if ((not system_message) or self.force_system_message) else "") + (
            "\n\n" + system_message[0] if system_message else "")).strip()

        return complete

    def __del__(self):
        """Close the bot."""

        if self.matrix_client:
            asyncio.run(self.matrix_client.close())

        if self.database:
            self.database.close()
