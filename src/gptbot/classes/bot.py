import markdown2
import tiktoken
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
    RoomMessageText,
    RoomSendResponse,
    SyncResponse,
    RoomMessageNotice,
    JoinError,
    RoomLeaveError,
    RoomSendError,
    RoomVisibility,
    RoomCreateError,
    RoomMessageMedia,
    DownloadError,
    RoomGetStateError,
    DiskDownloadResponse,
    MemoryDownloadResponse,
    LoginError,
)
from nio.store import SqliteStore


from typing import Optional, List, Any, Union
from configparser import ConfigParser
from datetime import datetime
from io import BytesIO
from pathlib import Path
from contextlib import closing

import uuid
import traceback
import json
import sqlite3

from .logging import Logger
from ..migrations import migrate
from ..callbacks import RESPONSE_CALLBACKS, EVENT_CALLBACKS
from ..commands import COMMANDS
from ..tools import TOOLS, Handover, StopProcessing
from .ai.base import BaseAI
from .exceptions import DownloadException


class GPTBot:
    # Default values
    database: Optional[sqlite3.Connection] = None
    database_path: Optional[str | Path] = None
    matrix_client: Optional[AsyncClient] = None
    sync_token: Optional[str] = None
    logger: Optional[Logger] = Logger()
    chat_api: Optional[BaseAI] = None
    image_api: Optional[BaseAI] = None
    classification_api: Optional[BaseAI] = None
    tts_api: Optional[BaseAI] = None
    stt_api: Optional[BaseAI] = None
    parcel_api: Optional[Any] = None
    calculation_api: Optional[Any] = None
    room_ignore_list: List[str] = []  # List of rooms to ignore invites from
    logo: Optional[Image.Image] = None
    logo_uri: Optional[str] = None
    config: ConfigParser = ConfigParser()

    # Properties

    @property
    def allowed_users(self) -> List[str]:
        """List of users allowed to use the bot.

        Returns:
            List[str]: List of user IDs. Defaults to [], which means all users are allowed.
        """
        try:
            return json.loads(self.config["GPTBot"]["AllowedUsers"])
        except Exception:
            return []

    @property
    def display_name(self) -> str:
        """Display name of the bot user.

        Returns:
            str: The display name of the bot user. Defaults to "GPTBot".
        """
        return self.config["GPTBot"].get("DisplayName", "GPTBot")

    @property
    def default_room_name(self) -> str:
        """Default name of rooms created by the bot.

        Returns:
            str: The default name of rooms created by the bot. Defaults to the display name of the bot.
        """
        return self.config["GPTBot"].get("DefaultRoomName", self.display_name)

    @property
    def default_system_message(self) -> str:
        """Default system message to include in rooms created by the bot.

        Returns:
            str: The default system message to include in rooms created by the bot. Defaults to "You are a helpful assistant.".
        """
        return self.config["GPTBot"].get(
            "SystemMessage",
            "You are a helpful assistant.",
        )

    @property
    def force_system_message(self) -> bool:
        """Whether to force the default system message to be included even if a custom room message is set.

        Returns:
            bool: Whether to force the default system message to be included even if a custom room message is set. Defaults to False.
        """
        return self.config["GPTBot"].getboolean("ForceSystemMessage", False)

    @property
    def operator(self) -> Optional[str]:
        """Operator of the bot.

        Returns:
            Optional[str]: The matrix user ID of the operator of the bot. Defaults to None.
        """
        return self.config["GPTBot"].get("Operator")

    @property
    def debug(self) -> bool:
        """Whether to enable debug logging.

        Returns:
            bool: Whether to enable debug logging. Defaults to False.
        """
        return self.config["GPTBot"].getboolean("Debug", False)

    @property
    def logo_path(self) -> str:
        """Path to the logo of the bot.

        Returns:
            str: The path to the logo of the bot. Defaults to "assets/logo.png" in the bot's directory.
        """
        return self.config["GPTBot"].get(
            "Logo", str(Path(__file__).parent.parent / "assets/logo.png")
        )

    @property
    def allow_model_override(self) -> bool:
        """Whether to allow per-room model overrides.

        Returns:
            bool: Whether to allow per-room model overrides. Defaults to False.
        """
        return self.config["GPTBot"].getboolean("AllowModelOverride", False)

    # User agent to use for HTTP requests
    USER_AGENT = "matrix-gptbot/dev (+https://kumig.it/kumitterer/matrix-gptbot)"

    @classmethod
    async def from_config(cls, config: ConfigParser):
        """Create a new GPTBot instance from a config file.

        Args:
            config (ConfigParser): ConfigParser instance with the bot's config.

        Returns:
            GPTBot: The new GPTBot instance.
        """

        # Create a new GPTBot instance
        bot = cls()
        bot.config = config

        # Set the database connection
        bot.database_path = (
            config["Database"]["Path"]
            if "Database" in config and "Path" in config["Database"]
            else None
        )
        bot.database = sqlite3.connect(bot.database_path) if bot.database_path else None

        # Override default values
        if "GPTBot" in config:
            if "LogLevel" in config["GPTBot"]:
                bot.logger = Logger(config["GPTBot"]["LogLevel"])

            bot.logger.log(f"Loading logo from {bot.logo_path}", "debug")

            if Path(bot.logo_path).exists() and Path(bot.logo_path).is_file():
                bot.logo = Image.open(bot.logo_path)

        # Set up OpenAI
        assert (
            "OpenAI" in config
        ), "OpenAI config not found"  # TODO: Update this to support other providers

        from .ai.openai import OpenAI

        openai_api = OpenAI(bot=bot, config=config["OpenAI"])

        if "Model" in config["OpenAI"]:
            bot.chat_api = openai_api
            bot.classification_api = openai_api

        if "ImageModel" in config["OpenAI"]:
            bot.image_api = openai_api

        if "TTSModel" in config["OpenAI"]:
            bot.tts_api = openai_api

        if "STTModel" in config["OpenAI"]:
            bot.stt_api = openai_api

        # Set up WolframAlpha
        if "WolframAlpha" in config:
            from .wolframalpha import WolframAlpha

            bot.calculation_api = WolframAlpha(
                config["WolframAlpha"]["APIKey"], bot.logger
            )

        # Set up TrackingMore
        if "TrackingMore" in config:
            from .trackingmore import TrackingMore

            bot.parcel_api = TrackingMore(config["TrackingMore"]["APIKey"], bot.logger)

        # Set up the Matrix client
        assert "Matrix" in config, "Matrix config not found"

        homeserver = config["Matrix"]["Homeserver"]

        if config.get("Matrix", "Password", fallback=""):
            if not config.get("Matrix", "UserID", fallback=""):
                raise Exception("Cannot log in: UserID not set in config")

            bot.matrix_client = AsyncClient(homeserver, user=config["Matrix"]["UserID"])
            login = await bot.matrix_client.login(password=config["Matrix"]["Password"])

            if isinstance(login, LoginError):
                raise Exception(f"Could not log in: {login.message}")

            config["Matrix"]["AccessToken"] = bot.matrix_client.access_token
            config["Matrix"]["DeviceID"] = bot.matrix_client.device_id
            config["Matrix"]["Password"] = ""

        else:
            bot.matrix_client = AsyncClient(homeserver)

            bot.matrix_client.access_token = config["Matrix"]["AccessToken"]
            bot.matrix_client.user_id = config["Matrix"].get("UserID")
            bot.matrix_client.device_id = config["Matrix"].get("DeviceID")

        # Return the new GPTBot instance and the (potentially modified) config
        return bot, config

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

    async def _last_n_messages(
        self,
        room: str | MatrixRoom,
        n: Optional[int],
        ignore_notices: bool = True,
    ):
        messages = []
        n = n or self.chat_api.max_messages
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        self.logger.log(
            f"Fetching last {2*n} messages from room {room_id} (starting at {self.sync_token})...",
            "debug",
        )

        response = await self.matrix_client.room_messages(
            room_id=room_id,
            start=self.sync_token,
            limit=2 * n,
        )

        if isinstance(response, RoomMessagesError):
            raise Exception(
                f"Error fetching messages: {response.message} (status code {response.status_code})",
                "error",
            )

        for event in response.chunk:
            try:
                event_type = event.type
            except AttributeError:
                try:
                    event_type = event.source["content"]["msgtype"]
                except KeyError:
                    if event.__class__.__name__ in ("RoomMemberEvent",):
                        self.logger.log(
                            f"Ignoring event of type {event.__class__.__name__}",
                            "debug",
                        )
                        continue
                    self.logger.log(f"Could not process event: {event}", "warning")
                    continue  # This is most likely not a message event

            if event_type.startswith("gptbot"):
                messages.append(event)

            elif isinstance(event, RoomMessageText):
                if event.body.split() == ["!gptbot", "ignoreolder"]:
                    break
                if (not event.body.startswith("!")) or (
                    event.body.split()[1] == "custom"
                ):
                    messages.append(event)

            elif isinstance(event, RoomMessageNotice):
                if not ignore_notices:
                    messages.append(event)

            elif isinstance(event, RoomMessageMedia):
                messages.append(event)

            if len(messages) >= n:
                break

        self.logger.log(f"Found {len(messages)} messages (limit: {n})", "debug")

        # Reverse the list so that messages are in chronological order
        return messages[::-1]

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

    async def call_tool(self, tool_call: dict, room: str, user: str, **kwargs):
        """Call a tool.

        Args:
            tool_call (dict): The tool call to make.
            room (str): The room to call the tool in.
            user (str): The user to call the tool as.
        """

        tool = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        self.logger.log(
            f"Calling tool {tool} with args {args} for user {user} in room {room}",
            "debug",
        )

        await self.send_message(
            room, f"Calling tool {tool} with arguments {args}.", True
        )

        try:
            tool_class = TOOLS[tool]
            result = await tool_class(**args, room=room, bot=self, user=user).run()
            await self.send_message(room, result, msgtype="gptbot.tool_result")
            return result

        except (Handover, StopProcessing):
            raise

        except KeyError:
            self.logger.log(f"Tool {tool} not found", "error")
            return "Error: Tool not found"

        except Exception as e:
            self.logger.log(f"Error calling tool {tool}: {e}", "error")
            return f"Error: Something went wrong calling tool {tool}"

    async def process_command(self, room: MatrixRoom, event: RoomMessageText):
        """Process a command. Called from the event_callback() method.
        Delegates to the appropriate command handler.

        Args:
            room (MatrixRoom): The room the command was sent in.
            event (RoomMessageText): The event containing the command.
        """

        self.logger.log(
            f"Received command {event.body} from {event.sender} in room {room.room_id}",
            "debug",
        )

        if event.body.startswith("* "):
            event.body = event.body[2:]

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

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "use_classification"),
            )
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
                or (
                    (
                        f"*:{user_id.split(':')[1]}" in self.allowed_users
                        or f"@*:{user_id.split(':')[1]}" in self.allowed_users
                    )
                    if not user_id.startswith("!") or user_id.startswith("#")
                    else False
                )
            )
            if self.allowed_users
            else True
        )

    def room_is_allowed(self, room_id: str) -> bool:
        """Check if everyone in a room is allowed to use the bot.

        Args:
            room_id (str): The room ID to check.

        Returns:
            bool: Whether everyone in the room is allowed to use the bot.
        """
        # TODO: Handle published aliases
        return self.user_is_allowed(room_id)

    async def event_callback(self, room: MatrixRoom, event: Event):
        """Callback for events.

        Args:
            room (MatrixRoom): The room the event was sent in.
            event (Event): The event.
        """

        if event.sender == self.matrix_client.user_id:
            return

        if not (
            self.user_is_allowed(event.sender) or self.room_is_allowed(room.room_id)
        ):
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

        asyncio.create_task(self._event_callback(room, event))

    def room_uses_timing(self, room: MatrixRoom):
        """Check if a room uses timing.

        Args:
            room (MatrixRoom): The room to check.

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

    async def _response_callback(self, response: Response):
        for response_type, callback in RESPONSE_CALLBACKS.items():
            if isinstance(response, response_type):
                await callback(response, self)

    async def response_callback(self, response: Response):
        asyncio.create_task(self._response_callback(response))

    async def accept_pending_invites(self):
        """Accept all pending invites."""

        assert self.matrix_client, "Matrix client not set up"

        invites = self.matrix_client.invited_rooms

        for invite in [k for k in invites.keys()]:
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
        self, room: MatrixRoom, image: bytes, message: Optional[str] = None
    ):
        """Send an image to a room.

        Args:
            room (MatrixRoom|str): The room to send the image to.
            image (bytes): The image to send.
            message (str, optional): The message to send with the image. Defaults to None.
        """

        if isinstance(room, MatrixRoom):
            room = room.room_id

        self.logger.log(
            f"Sending image of size {len(image)} bytes to room {room}", "debug"
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

        await self.matrix_client.room_send(room, "m.room.message", content)

        self.logger.log("Sent image", "debug")

    async def send_file(
        self, room: MatrixRoom, file: bytes, filename: str, mime: str, msgtype: str
    ):
        """Send a file to a room.

        Args:
            room (MatrixRoom|str): The room to send the file to.
            file (bytes): The file to send.
            filename (str): The name of the file.
            mime (str): The MIME type of the file.
        """

        if isinstance(room, MatrixRoom):
            room = room.room_id

        self.logger.log(
            f"Sending file of size {len(file)} bytes to room {room}", "debug"
        )

        content_uri = await self.upload_file(file, filename, mime)

        self.logger.log("Uploaded file - sending message...", "debug")

        content = {
            "body": filename,
            "info": {"mimetype": mime, "size": len(file)},
            "msgtype": msgtype,
            "url": content_uri,
        }

        await self.matrix_client.room_send(room, "m.room.message", content)

        self.logger.log("Sent file", "debug")

    async def send_message(
        self,
        room: MatrixRoom | str,
        message: str,
        notice: bool = False,
        msgtype: Optional[str] = None,
    ):
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

        msgtype = msgtype if msgtype else "m.notice" if notice else "m.text"

        if not msgtype.startswith("gptbot."):
            msgcontent = {
                "msgtype": msgtype,
                "body": message,
                "format": "org.matrix.custom.html",
                "formatted_body": formatted_body,
            }

        else:
            msgcontent = {
                "msgtype": msgtype,
                "content": message,
            }

        content = None

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
        self, message: Event | str, room: MatrixRoom | str, api: str, tokens: int
    ):
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
            (message, room, tokens, api, datetime.now()),
        )

    async def get_state_event(
        self, room: MatrixRoom | str, event_type: str, state_key: Optional[str] = None
    ):
        if isinstance(room, MatrixRoom):
            room = room.room_id

        state = await self.matrix_client.room_get_state(room)

        if isinstance(state, RoomGetStateError):
            self.logger.log(f"Could not get state for room {room}")

        for event in state.events:
            if event["type"] == event_type:
                if state_key is None or event["state_key"] == state_key:
                    return event

    async def run(self):
        """Start the bot."""

        # Set up the Matrix client

        assert self.matrix_client, "Matrix client not set up"
        assert self.matrix_client.access_token, "Access token not set up"

        if not self.matrix_client.user_id:
            self.matrix_client.user_id = await self._get_user_id()

        if not self.matrix_client.device_id:
            self.matrix_client.device_id = await self._get_device_id()

        if not self.database:
            self.database = sqlite3.connect(
                Path(__file__).parent.parent / "database.db"
            )

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

        matrix_store = SqliteStore
        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=False, store=matrix_store
        )
        self.matrix_client.config = client_config

        # Run initial sync (includes joining rooms)

        self.logger.log("Running initial sync...", "debug")

        sync = await self.matrix_client.sync(timeout=30000, full_state=True)
        if isinstance(sync, SyncResponse):
            await self.response_callback(sync)
        else:
            self.logger.log(f"Initial sync failed, aborting: {sync}", "critical")
            exit(1)

        # Set up callbacks

        self.logger.log("Setting up callbacks...", "debug")

        self.matrix_client.add_event_callback(self.event_callback, Event)
        self.matrix_client.add_response_callback(self.response_callback, Response)

        # Set custom name / logo

        if self.display_name:
            self.logger.log(f"Setting display name to {self.display_name}", "debug")
            asyncio.create_task(self.matrix_client.set_displayname(self.display_name))
        if self.logo:
            self.logger.log("Setting avatar...")
            logo_bio = BytesIO()
            self.logo.save(logo_bio, format=self.logo.format)
            uri = await self.upload_file(
                logo_bio.getvalue(), "logo", Image.MIME[self.logo.format]
            )
            self.logo_uri = uri

            asyncio.create_task(self.matrix_client.set_avatar(uri))

            for room in self.matrix_client.rooms.keys():
                room_avatar = await self.get_state_event(room, "m.room.avatar")
                if not room_avatar:
                    self.logger.log(f"Setting avatar for {room}...", "debug")
                    asyncio.create_task(
                        self.matrix_client.room_put_state(
                            room, "m.room.avatar", {"url": uri}, ""
                        )
                    )

        # Start syncing events
        self.logger.log("Starting sync loop...", "warning")
        try:
            await self.matrix_client.sync_forever(timeout=30000, full_state=True)
        finally:
            self.logger.log("Syncing one last time...", "warning")
            await self.matrix_client.sync(timeout=30000, full_state=True)

    async def create_space(self, name, visibility=RoomVisibility.private) -> str:
        """Create a space.

        Args:
            name (str): The name of the space.
            visibility (RoomVisibility, optional): The visibility of the space. Defaults to RoomVisibility.private.

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
        self, space: MatrixRoom | str, rooms: List[MatrixRoom | str]
    ):
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

    def room_uses_stt(self, room: MatrixRoom | str) -> bool:
        """Check if a room uses STT.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            bool: Whether the room uses STT.
        """
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "stt"),
            )
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    def room_uses_tts(self, room: MatrixRoom | str) -> bool:
        """Check if a room uses TTS.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            bool: Whether the room uses TTS.
        """
        room_id = room.room_id if isinstance(room, MatrixRoom) else room

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room_id, "tts"),
            )
            result = cursor.fetchone()

        return False if not result else bool(int(result[0]))

    def respond_to_room_messages(self, room: MatrixRoom | str) -> bool:
        """Check whether the bot should respond to all messages sent in a room.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            bool: Whether the bot should respond to all messages sent in the room.
        """

        if isinstance(room, MatrixRoom):
            room = room.room_id

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room, "always_reply"),
            )
            result = cursor.fetchone()

        return True if not result else bool(int(result[0]))

    async def get_room_model(self, room: MatrixRoom | str) -> str:
        """Get the model used for a room.

        Args:
            room (MatrixRoom | str): The room to check.

        Returns:
            str: The model used for the room.
        """

        if isinstance(room, MatrixRoom):
            room = room.room_id

        with closing(self.database.cursor()) as cursor:
            cursor.execute(
                "SELECT value FROM room_settings WHERE room_id = ? AND setting = ?",
                (room, "model"),
            )
            result = cursor.fetchone()

        return result[0] if result else self.chat_api.chat_model

    async def process_query(
        self, room: MatrixRoom, event: RoomMessageText, from_chat_command: bool = False
    ):
        """Process a query message. Generates a response and sends it to the room.

        Args:
            room (MatrixRoom): The room the message was sent in.
            event (RoomMessageText): The event that triggered the query.
            from_chat_command (bool, optional): Whether the query was sent via the `!gptbot chat` command. Defaults to False.
        """

        if not (
            from_chat_command
            or self.respond_to_room_messages(room)
            or self.matrix_client.user_id in event.body
        ):
            return

        await self.matrix_client.room_typing(room.room_id, True)

        await self.matrix_client.room_read_markers(room.room_id, event.event_id)

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
            last_messages = await self._last_n_messages(
                room.room_id, self.chat_api.max_messages
            )
            self.logger.log(f"Last messages: {last_messages}", "debug")
        except Exception as e:
            self.logger.log(f"Error getting last messages: {e}", "error")
            await self.send_message(
                room, "Something went wrong. Please try again.", True
            )
            return

        system_message = self.get_system_message(room)

        chat_messages = await self.chat_api.prepare_messages(
            event, last_messages, system_message
        )

        # Check for a model override
        if self.allow_model_override:
            model = await self.get_room_model(room)
        else:
            model = self.chat_api.chat_model

        try:
            response, tokens_used = await self.chat_api.generate_chat_response(
                chat_messages, user=event.sender, room=room.room_id, model=model
            )
        except Exception as e:
            print(traceback.format_exc())
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

            if self.room_uses_tts(room):
                self.logger.log("TTS enabled for room", "debug")

                try:
                    audio = await self.tts_api.text_to_speech(response)
                    await self.send_file(room, audio, response, "audio/mpeg", "m.audio")
                    return

                except Exception as e:
                    self.logger.log(f"Error generating audio: {e}", "error")
                    await self.send_message(
                        room, "Something went wrong generating audio file.", True
                    )
                    
                    if self.debug:
                        await self.send_message(
                            room, f"Error: {e}\n\n```\n{traceback.format_exc()}\n```", True
                        )

            await self.send_message(room, response)

        await self.matrix_client.room_typing(room.room_id, False)

    async def download_file(
        self, mxc: str, raise_error: bool = False
    ) -> Union[DiskDownloadResponse, MemoryDownloadResponse]:
        """Download a file from the homeserver.

        Args:
            mxc (str): The MXC URI of the file to download.

        Returns:
            Optional[bytes]: The downloaded file, or None if there was an error.
        """

        download = await self.matrix_client.download(mxc)

        if isinstance(download, DownloadError):
            self.logger.log(f"Error downloading file: {download.message}", "error")
            if raise_error:
                raise DownloadException(download.message)
            return

        return download

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
