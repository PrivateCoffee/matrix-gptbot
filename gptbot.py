import os
import inspect
import logging
import signal
import random

import openai
import asyncio
import markdown2
import tiktoken
import duckdb

from nio import AsyncClient, RoomMessageText, MatrixRoom, Event, InviteEvent
from nio.api import MessageDirection
from nio.responses import RoomMessagesError, SyncResponse, RoomRedactError

from configparser import ConfigParser
from datetime import datetime
from argparse import ArgumentParser
from typing import List, Dict, Union, Optional

from commands import COMMANDS


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

        markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
        formatted_body = markdowner.convert(response)

        message = await client.room_send(
            room.room_id, "m.room.message",
            {"msgtype": "m.text", "body": response,
             "format": "org.matrix.custom.html", "formatted_body": formatted_body}
        )

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

        await client.room_send(
            room.room_id, "m.room.message", {
                "msgtype": "m.notice", "body": "Sorry, I'm having trouble connecting to the GPT API right now. Please try again later."}
        )
        print("No response from GPT API")

    await client.room_typing(room.room_id, False)


async def process_command(room: MatrixRoom, event: RoomMessageText, context: Optional[dict] = None):
    context = context or CONTEXT

    logging(
        f"Received command {event.body} from {event.sender} in room {room.room_id}")
    command = event.body.split()[1] if event.body.split()[1:] else None
    await COMMANDS.get(command, COMMANDS[None])(room, event, context)


async def message_callback(room: MatrixRoom, event: RoomMessageText, **kwargs):
    context = kwargs.get("context") or CONTEXT
    
    logging(f"Received message from {event.sender} in room {room.room_id}")

    if event.sender == context["client"].user_id:
        logging("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot"):
        await process_command(room, event)

    elif event.body.startswith("!"):
        logging("Might be a command, but not for this bot - ignoring")

    else:
        await process_query(room, event, context=context)


async def room_invite_callback(room: MatrixRoom, event: InviteEvent, **kwargs):
    client = kwargs.get("client") or CONTEXT["client"]

    logging(f"Received invite to room {room.room_id} - joining...")

    await client.join(room.room_id)
    await client.room_send(
        room.room_id,
        "m.room.message",
        {"msgtype": "m.text",
            "body": "Hello! I'm a helpful assistant. How can I help you today?"}
    )


async def accept_pending_invites(client: Optional[AsyncClient] = None):
    client = client or CONTEXT["client"]

    logging("Accepting pending invites...")

    for room_id in list(client.invited_rooms.keys()):
        logging(f"Joining room {room_id}...")

        await client.join(room_id)
        await client.room_send(
            room_id,
            "m.room.message",
            {"msgtype": "m.text",
                "body": "Hello! I'm a helpful assistant. How can I help you today?"}
        )


async def sync_cb(response, write_global: bool = True):
    logging(
        f"Sync response received (next batch: {response.next_batch})", "debug")
    SYNC_TOKEN = response.next_batch

    if write_global:
        global CONTEXT
        CONTEXT["sync_token"] = SYNC_TOKEN


async def main(client: Optional[AsyncClient] = None):
    client = client or CONTEXT["client"]

    if not client.user_id:
        whoami = await client.whoami()
        client.user_id = whoami.user_id

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
    client.add_event_callback(room_invite_callback, InviteEvent)

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


if __name__ == "__main__":
    # Parse command line arguments
    parser = ArgumentParser()
    parser.add_argument(
        "--config", help="Path to config file (default: config.ini in working directory)", default="config.ini")
    args = parser.parse_args()

    # Read config file
    config = ConfigParser()
    config.read(args.config)

    # Set up Matrix client
    try:
        assert "Matrix" in config
        assert "Homeserver" in config["Matrix"]
        assert "AccessToken" in config["Matrix"]
    except:
        logging("Matrix config not found or incomplete", "critical")
        exit(1)

    CONTEXT["client"] = AsyncClient(config["Matrix"]["Homeserver"])

    CONTEXT["client"].access_token = config["Matrix"]["AccessToken"]
    CONTEXT["client"].user_id = config["Matrix"].get("UserID")

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

    # Set up database
    if "Database" in config and config["Database"].get("Path"):
        CONTEXT["database"] = initialize_database(config["Database"]["Path"])

    # Listen for SIGTERM

    def sigterm_handler(_signo, _stack_frame):
        logging("Received SIGTERM - exiting...")
        exit()

    signal.signal(signal.SIGTERM, sigterm_handler)

    # Start bot loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging("Received KeyboardInterrupt - exiting...")
    except SystemExit:
        logging("Received SIGTERM - exiting...")
    finally:
        if CONTEXT["database"]:
            CONTEXT["database"].close()
