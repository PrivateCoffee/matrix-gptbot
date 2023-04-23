import os
import inspect
import logging
import signal
import random
import uuid

import openai
import asyncio
import markdown2
import tiktoken
import duckdb

from nio import AsyncClient, RoomMessageText, MatrixRoom, Event, InviteEvent, AsyncClientConfig, MegolmEvent, GroupEncryptionError, EncryptionError, HttpClient, Api
from nio.api import MessageDirection
from nio.responses import RoomMessagesError, SyncResponse, RoomRedactError, WhoamiResponse, JoinResponse, RoomSendResponse
from nio.crypto import Olm

from configparser import ConfigParser
from datetime import datetime
from argparse import ArgumentParser
from typing import List, Dict, Union, Optional

from commands import COMMANDS
from classes import DuckDBStore


def logging(message: str, log_level: str = "info"):
    caller = inspect.currentframe().f_back.f_code.co_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
    print(f"[{timestamp}] - {caller} - [{log_level.upper()}] {message}")


CONTEXT = {
    "database": False,
    "default_room_name": "GPTBot",
    "system_message": "You are a helpful assistant.",
    "max_tokens": 3000,
    "max_messages": 20,
    "model": "gpt-3.5-turbo",
    "client": None,
    "sync_token": None,
    "logger": logging
}


async def gpt_query(messages: list, model: Optional[str] = None):
    model = model or CONTEXT["model"]

    logging(f"Querying GPT with {len(messages)} messages")
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages
        )
        result_text = response.choices[0].message['content']
        tokens_used = response.usage["total_tokens"]
        logging(f"Used {tokens_used} tokens")
        return result_text, tokens_used

    except Exception as e:
        logging(f"Error during GPT API call: {e}", "error")
        return None, 0


async def fetch_last_n_messages(room_id: str, n: Optional[int] = None,
                                client: Optional[AsyncClient] = None, sync_token: Optional[str] = None):
    messages = []

    n = n or CONTEXT["max_messages"]
    client = client or CONTEXT["client"]
    sync_token = sync_token or CONTEXT["sync_token"]

    logging(
        f"Fetching last {2*n} messages from room {room_id} (starting at {sync_token})...")

    response = await client.room_messages(
        room_id=room_id,
        start=sync_token,
        limit=2*n,
    )

    if isinstance(response, RoomMessagesError):
        logging(
            f"Error fetching messages: {response.message} (status code {response.status_code})", "error")
        return []

    for event in response.chunk:
        if len(messages) >= n:
            break
        if isinstance(event, MegolmEvent):
            try:
                event = await client.decrypt_event(event)
            except (GroupEncryptionError, EncryptionError):
                logging(
                    f"Could not decrypt message {event.event_id} in room {room_id}", "error")
                continue
        if isinstance(event, RoomMessageText):
            if event.body.startswith("!gptbot ignoreolder"):
                break
            if not event.body.startswith("!"):
                messages.append(event)

    logging(f"Found {len(messages)} messages (limit: {n})")

    # Reverse the list so that messages are in chronological order
    return messages[::-1]


def truncate_messages_to_fit_tokens(messages: list, max_tokens: Optional[int] = None,
                                    model: Optional[str] = None, system_message: Optional[str] = None):
    max_tokens = max_tokens or CONTEXT["max_tokens"]
    model = model or CONTEXT["model"]
    system_message = system_message or CONTEXT["system_message"]

    encoding = tiktoken.encoding_for_model(model)
    total_tokens = 0

    system_message_tokens = len(encoding.encode(system_message)) + 1

    if system_message_tokens > max_tokens:
        logging(
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


async def process_query(room: MatrixRoom, event: RoomMessageText, **kwargs):

    client = kwargs.get("client") or CONTEXT["client"]
    database = kwargs.get("database") or CONTEXT["database"]
    system_message = kwargs.get("system_message") or CONTEXT["system_message"]
    max_tokens = kwargs.get("max_tokens") or CONTEXT["max_tokens"]

    await client.room_typing(room.room_id, True)

    await client.room_read_markers(room.room_id, event.event_id)

    last_messages = await fetch_last_n_messages(room.room_id, 20)

    chat_messages = [{"role": "system", "content": system_message}]

    for message in last_messages:
        role = "assistant" if message.sender == client.user_id else "user"
        if not message.event_id == event.event_id:
            chat_messages.append({"role": role, "content": message.body})

    chat_messages.append({"role": "user", "content": event.body})

    # Truncate messages to fit within the token limit
    truncated_messages = truncate_messages_to_fit_tokens(
        chat_messages, max_tokens - 1)

    response, tokens_used = await gpt_query(truncated_messages)

    if response:
        logging(f"Sending response to room {room.room_id}...")

        # Convert markdown to HTML

        message = await send_message(room, response)

        if database:
            logging("Logging tokens used...")

            with database.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO token_usage (message_id, room_id, tokens, timestamp) VALUES (?, ?, ?, ?)",
                    (message.event_id, room.room_id, tokens_used, datetime.now()))
                database.commit()
    else:
        # Send a notice to the room if there was an error

        logging("Error during GPT API call - sending notice to room")
        send_message(
            room, "Sorry, I'm having trouble connecting to the GPT API right now. Please try again later.", True)
        print("No response from GPT API")

    await client.room_typing(room.room_id, False)


async def process_command(room: MatrixRoom, event: RoomMessageText, context: Optional[dict] = None):
    context = context or CONTEXT

    logging(
        f"Received command {event.body} from {event.sender} in room {room.room_id}")
    command = event.body.split()[1] if event.body.split()[1:] else None

    message = await COMMANDS.get(command, COMMANDS[None])(room, event, context)

    if message:
        room_id, event, content = message
        await send_message(context["client"].rooms[room_id], content["body"],
                           True if content["msgtype"] == "m.notice" else False, context["client"])


async def message_callback(room: MatrixRoom, event: RoomMessageText | MegolmEvent, **kwargs):
    context = kwargs.get("context") or CONTEXT

    logging(f"Received message from {event.sender} in room {room.room_id}")

    if isinstance(event, MegolmEvent):
        try:
            event = await context["client"].decrypt_event(event)
        except Exception as e:
            try:
                logging("Requesting new encryption keys...")
                await context["client"].request_room_key(event)
            except:
                pass

            logging(f"Error decrypting message: {e}", "error")
            await send_message(room, "Sorry, I couldn't decrypt that message. Please try again later or switch to a room without encryption.", True, context["client"])
            return

    if event.sender == context["client"].user_id:
        logging("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot"):
        await process_command(room, event)

    elif event.body.startswith("!"):
        logging("Might be a command, but not for this bot - ignoring")

    else:
        await process_query(room, event, context=context)


async def room_invite_callback(room: MatrixRoom, event: InviteEvent, **kwargs):
    client: AsyncClient = kwargs.get("client") or CONTEXT["client"]

    if room.room_id in client.rooms:
        logging(f"Already in room {room.room_id} - ignoring invite")
        return

    logging(f"Received invite to room {room.room_id} - joining...")

    response = await client.join(room.room_id)
    if isinstance(response, JoinResponse):
        await send_message(room, "Hello! I'm a helpful assistant. How can I help you today?", client)
    else:
        logging(f"Error joining room {room.room_id}: {response}", "error")


async def send_message(room: MatrixRoom, message: str, notice: bool = False, client: Optional[AsyncClient] = None):
    client = client or CONTEXT["client"]

    markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
    formatted_body = markdowner.convert(message)

    msgtype = "m.notice" if notice else "m.text"

    msgcontent = {"msgtype": msgtype, "body": message,
                  "format": "org.matrix.custom.html", "formatted_body": formatted_body}

    content = None

    if client.olm and room.encrypted:
        try:
            if not room.members_synced:
                responses = []
                responses.append(await client.joined_members(room.room_id))

            if client.olm.should_share_group_session(room.room_id):
                try:
                    event = client.sharing_session[room.room_id]
                    await event.wait()
                except KeyError:
                    await client.share_group_session(
                        room.room_id,
                        ignore_unverified_devices=True,
                    )

            if msgtype != "m.reaction":
                response = client.encrypt(room.room_id, "m.room.message", msgcontent)
                msgtype, content = response

        except Exception as e:
            logging(
                f"Error encrypting message: {e} - sending unencrypted", "error")
            raise

    if not content:
        msgtype = "m.room.message"
        content = msgcontent

    method, path, data = Api.room_send(
        client.access_token, room.room_id, msgtype, content, uuid.uuid4()
    )

    return await client._send(RoomSendResponse, method, path, data, (room.room_id,))


async def accept_pending_invites(client: Optional[AsyncClient] = None):
    client = client or CONTEXT["client"]

    logging("Accepting pending invites...")

    for room_id in list(client.invited_rooms.keys()):
        logging(f"Joining room {room_id}...")

        response = await client.join(room_id)

        if isinstance(response, JoinResponse):
            logging(response, "debug")
            rooms = await client.joined_rooms()
            await send_message(rooms[room_id], "Hello! I'm a helpful assistant. How can I help you today?", client)
        else:
            logging(f"Error joining room {room_id}: {response}", "error")


async def sync_cb(response, write_global: bool = True):
    logging(
        f"Sync response received (next batch: {response.next_batch})", "debug")
    SYNC_TOKEN = response.next_batch

    if write_global:
        global CONTEXT
        CONTEXT["sync_token"] = SYNC_TOKEN


async def test_callback(room: MatrixRoom, event: Event, **kwargs):
    logging(
        f"Received event {event.__class__.__name__} in room {room.room_id}", "debug")


async def init(config: ConfigParser):
    # Set up Matrix client
    try:
        assert "Matrix" in config
        assert "Homeserver" in config["Matrix"]
        assert "AccessToken" in config["Matrix"]
    except:
        logging("Matrix config not found or incomplete", "critical")
        exit(1)

    homeserver = config["Matrix"]["Homeserver"]
    access_token = config["Matrix"]["AccessToken"]

    device_id, user_id = await get_device_id(access_token, homeserver)

    device_id = config["Matrix"].get("DeviceID", device_id)
    user_id = config["Matrix"].get("UserID", user_id)

    # Set up database
    if "Database" in config and config["Database"].get("Path"):
        database = CONTEXT["database"] = initialize_database(
            config["Database"]["Path"])
        matrix_store = DuckDBStore

        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=True, store=matrix_store)

    else:
        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=False)

    client = AsyncClient(
        config["Matrix"]["Homeserver"], config=client_config)

    if client.config.encryption_enabled:
        client.store = client.config.store(
            user_id,
            device_id,
            database
        )
        assert client.store

        client.olm = Olm(client.user_id, client.device_id, client.store)
        client.encrypted_rooms = client.store.load_encrypted_rooms()

    CONTEXT["client"] = client

    CONTEXT["client"].access_token = config["Matrix"]["AccessToken"]
    CONTEXT["client"].user_id = user_id
    CONTEXT["client"].device_id = device_id

    # Set up GPT API
    try:
        assert "OpenAI" in config
        assert "APIKey" in config["OpenAI"]
    except:
        logging("OpenAI config not found or incomplete", "critical")
        exit(1)

    openai.api_key = config["OpenAI"]["APIKey"]

    if "Model" in config["OpenAI"]:
        CONTEXT["model"] = config["OpenAI"]["Model"]

    if "MaxTokens" in config["OpenAI"]:
        CONTEXT["max_tokens"] = int(config["OpenAI"]["MaxTokens"])

    if "MaxMessages" in config["OpenAI"]:
        CONTEXT["max_messages"] = int(config["OpenAI"]["MaxMessages"])

    # Listen for SIGTERM

    def sigterm_handler(_signo, _stack_frame):
        logging("Received SIGTERM - exiting...")
        exit()

    signal.signal(signal.SIGTERM, sigterm_handler)


async def main(config: Optional[ConfigParser] = None, client: Optional[AsyncClient] = None):
    if not client and not CONTEXT.get("client"):
        await init(config)

    client = client or CONTEXT["client"]

    try:
        assert client.user_id
    except AssertionError:
        logging(
            "Failed to get user ID - check your access token or try setting it manually", "critical")
        await client.close()
        return

    logging("Starting bot...")

    client.add_response_callback(sync_cb, SyncResponse)

    logging("Syncing...")

    await client.sync(timeout=30000)

    client.add_event_callback(message_callback, RoomMessageText)
    client.add_event_callback(message_callback, MegolmEvent)
    client.add_event_callback(room_invite_callback, InviteEvent)
    client.add_event_callback(test_callback, Event)

    await accept_pending_invites()  # Accept pending invites

    logging("Bot started")

    try:
        # Continue syncing events
        await client.sync_forever(timeout=30000)
    finally:
        logging("Syncing one last time...")
        await client.sync(timeout=30000)
        await client.close()  # Properly close the aiohttp client session
        logging("Bot stopped")


def initialize_database(path: os.PathLike):
    logging("Initializing database...")
    database = duckdb.connect(path)

    with database.cursor() as cursor:
        # Get the latest migration ID if the migrations table exists
        try:
            cursor.execute(
                """
                SELECT MAX(id) FROM migrations
                """
            )

            latest_migration = int(cursor.fetchone()[0])
        except:
            latest_migration = 0

        # Version 1

        if latest_migration < 1:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    message_id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL
                )
                """
            )

            cursor.execute(
                "INSERT INTO migrations (id, timestamp) VALUES (1, ?)",
                (datetime.now(),)
            )

        database.commit()

        return database


async def get_device_id(access_token, homeserver):
    client = AsyncClient(homeserver)
    client.access_token = access_token

    logging(f"Obtaining device ID for access token {access_token}...", "debug")
    response = await client.whoami()
    if isinstance(response, WhoamiResponse):
        logging(
            f"Authenticated as {response.user_id}.")
        user_id = response.user_id
        devices = await client.devices()
        device_id = devices.devices[0].id

        await client.close()

        return device_id, user_id

    else:
        logging(f"Failed to obtain device ID: {response}", "error")

        await client.close()

        return None, None


if __name__ == "__main__":
    # Parse command line arguments
    parser = ArgumentParser()
    parser.add_argument(
        "--config", help="Path to config file (default: config.ini in working directory)", default="config.ini")
    args = parser.parse_args()

    # Read config file
    config = ConfigParser()
    config.read(args.config)

    # Start bot loop
    try:
        asyncio.run(main(config))
    except KeyboardInterrupt:
        logging("Received KeyboardInterrupt - exiting...")
    except SystemExit:
        logging("Received SIGTERM - exiting...")
    finally:
        if CONTEXT["database"]:
            CONTEXT["database"].close()
