import os
import inspect
import logging
import signal

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

# Globals

DATABASE = False
DEFAULT_ROOM_NAME = "GPTBot"
SYSTEM_MESSAGE = "You are a helpful assistant. "
MAX_TOKENS = 3000
MAX_MESSAGES = 20
DEFAULT_MODEL = "gpt-3.5-turbo"

# Set up Matrix client
MATRIX_CLIENT = None
SYNC_TOKEN = None


def logging(message, log_level="info"):
    caller = inspect.currentframe().f_back.f_code.co_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
    print(f"[{timestamp}] - {caller} - [{log_level.upper()}] {message}")


async def gpt_query(messages, model=DEFAULT_MODEL):
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


async def fetch_last_n_messages(room_id, n=MAX_MESSAGES):
    global SYNC_TOKEN, MATRIX_CLIENT

    messages = []

    logging(
        f"Fetching last {2*n} messages from room {room_id} (starting at {SYNC_TOKEN})...")

    response = await MATRIX_CLIENT.room_messages(
        room_id=room_id,
        start=SYNC_TOKEN,
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
            if not event.body.startswith("!"):
                messages.append(event)

    logging(f"Found {len(messages)} messages (limit: {n})")

    # Reverse the list so that messages are in chronological order
    return messages[::-1]


def truncate_messages_to_fit_tokens(messages, max_tokens=MAX_TOKENS, model=DEFAULT_MODEL):
    global SYSTEM_MESSAGE

    encoding = tiktoken.encoding_for_model(model)
    total_tokens = 0

    system_message_tokens = len(encoding.encode(SYSTEM_MESSAGE)) + 1

    if system_message_tokens > max_tokens:
        logging(
            f"System message is too long to fit within token limit ({system_message_tokens} tokens) - cannot proceed", "error")
        return []

    total_tokens += system_message_tokens

    total_tokens = len(SYSTEM_MESSAGE) + 1
    truncated_messages = []

    for message in [messages[0]] + list(reversed(messages[1:])):
        content = message["content"]
        tokens = len(encoding.encode(content)) + 1
        if total_tokens + tokens > max_tokens:
            break
        total_tokens += tokens
        truncated_messages.append(message)

    return [truncated_messages[0]] + list(reversed(truncated_messages[1:]))


async def process_query(room: MatrixRoom, event: RoomMessageText):
    global MATRIX_CLIENT, DATABASE, SYSTEM_MESSAGE

    await MATRIX_CLIENT.room_typing(room.room_id, True)

    await MATRIX_CLIENT.room_read_markers(room.room_id, event.event_id)

    last_messages = await fetch_last_n_messages(room.room_id, 20)

    chat_messages = [{"role": "system", "content": SYSTEM_MESSAGE}]

    for message in last_messages:
        role = "assistant" if message.sender == MATRIX_CLIENT.user_id else "user"
        if not message.event_id == event.event_id:
            chat_messages.append({"role": role, "content": message.body})

    chat_messages.append({"role": "user", "content": event.body})

    # Truncate messages to fit within the token limit
    truncated_messages = truncate_messages_to_fit_tokens(
        chat_messages, MAX_TOKENS - 1)

    response, tokens_used = await gpt_query(truncated_messages)

    if response:
        logging(f"Sending response to room {room.room_id}...")

        # Convert markdown to HTML

        markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
        formatted_body = markdowner.convert(response)

        message = await MATRIX_CLIENT.room_send(
            room.room_id, "m.room.message",
            {"msgtype": "m.text", "body": response,
             "format": "org.matrix.custom.html", "formatted_body": formatted_body}
        )

        if DATABASE:
            logging("Logging tokens used...")

            with DATABASE.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO token_usage (message_id, room_id, tokens, timestamp) VALUES (?, ?, ?, ?)", 
                    (message.event_id, room.room_id, tokens_used, datetime.now()))
                DATABASE.commit()
    else:
        # Send a notice to the room if there was an error

        logging("Error during GPT API call - sending notice to room")

        await MATRIX_CLIENT.room_send(
            room.room_id, "m.room.message", {
                "msgtype": "m.notice", "body": "Sorry, I'm having trouble connecting to the GPT API right now. Please try again later."}
        )
        print("No response from GPT API")

    await MATRIX_CLIENT.room_typing(room.room_id, False)


async def command_newroom(room: MatrixRoom, event: RoomMessageText):
    room_name = " ".join(event.body.split()[2:]) or DEFAULT_ROOM_NAME

    logging("Creating new room...")
    new_room = await MATRIX_CLIENT.room_create(name=room_name)

    logging(f"Inviting {event.sender} to new room...")
    await MATRIX_CLIENT.room_invite(new_room.room_id, event.sender)
    await MATRIX_CLIENT.room_put_state(
        new_room.room_id, "m.room.power_levels", {"users": {event.sender: 100}})

    await MATRIX_CLIENT.room_send(
        new_room.room_id, "m.room.message", {"msgtype": "m.text", "body": "Welcome to the new room!"})


async def command_help(room: MatrixRoom, event: RoomMessageText):
    await MATRIX_CLIENT.room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": """Available commands:

!gptbot help - Show this message
!gptbot newroom <room name> - Create a new room and invite yourself to it
!gptbot stats - Show usage statistics for this room
!gptbot botinfo - Show information about the bot
"""}
    )


async def command_stats(room: MatrixRoom, event: RoomMessageText):
    global DATABASE, MATRIX_CLIENT

    logging("Showing stats...")

    if not DATABASE:
        logging("No database connection - cannot show stats")
        return

    with DATABASE.cursor() as cursor:
        cursor.execute(
            "SELECT SUM(tokens) FROM token_usage WHERE room_id = ?", (room.room_id,))
        total_tokens = cursor.fetchone()[0] or 0

    await MATRIX_CLIENT.room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": f"Total tokens used: {total_tokens}"}
    )


async def command_unknown(room: MatrixRoom, event: RoomMessageText):
    global MATRIX_CLIENT

    logging("Unknown command")

    await MATRIX_CLIENT.room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": "Unknown command - try !gptbot help"}
    )


async def command_botinfo(room: MatrixRoom, event: RoomMessageText):
    global MATRIX_CLIENT

    logging("Showing bot info...")

    await MATRIX_CLIENT.room_send(
        room.room_id, "m.room.message", {"msgtype": "m.notice",
                                         "body": f"""GPT Info:

Model: {DEFAULT_MODEL}
Maximum context tokens: {MAX_TOKENS}
Maximum context messages: {MAX_MESSAGES}
System message: {SYSTEM_MESSAGE}

Room info:

Bot user ID: {MATRIX_CLIENT.user_id}
Current room ID: {room.room_id}

For usage statistics, run !gptbot stats
"""})

COMMANDS = {
    "help": command_help,
    "newroom": command_newroom,
    "stats": command_stats,
    "botinfo": command_botinfo
}


async def process_command(room: MatrixRoom, event: RoomMessageText):
    global COMMANDS

    logging(
        f"Received command {event.body} from {event.sender} in room {room.room_id}")
    command = event.body.split()[1] if event.body.split()[1:] else None
    await COMMANDS.get(command, command_unknown)(room, event)


async def message_callback(room: MatrixRoom, event: RoomMessageText):
    global DEFAULT_ROOM_NAME, MATRIX_CLIENT, SYSTEM_MESSAGE, DATABASE, MAX_TOKENS

    logging(f"Received message from {event.sender} in room {room.room_id}")

    if event.sender == MATRIX_CLIENT.user_id:
        logging("Message is from bot itself - ignoring")

    elif event.body.startswith("!gptbot"):
        await process_command(room, event)

    elif event.body.startswith("!"):
        logging("Might be a command, but not for this bot - ignoring")

    else:
        await process_query(room, event)


async def room_invite_callback(room: MatrixRoom, event):
    global MATRIX_CLIENT

    logging(f"Received invite to room {room.room_id} - joining...")

    await MATRIX_CLIENT.join(room.room_id)
    await MATRIX_CLIENT.room_send(
        room.room_id,
        "m.room.message",
        {"msgtype": "m.text",
            "body": "Hello! I'm a helpful assistant. How can I help you today?"}
    )


async def accept_pending_invites():
    global MATRIX_CLIENT

    logging("Accepting pending invites...")

    for room_id in list(MATRIX_CLIENT.invited_rooms.keys()):
        logging(f"Joining room {room_id}...")

        await MATRIX_CLIENT.join(room_id)
        await MATRIX_CLIENT.room_send(
            room_id,
            "m.room.message",
            {"msgtype": "m.text",
                "body": "Hello! I'm a helpful assistant. How can I help you today?"}
        )


async def sync_cb(response):
    global SYNC_TOKEN

    logging(
        f"Sync response received (next batch: {response.next_batch})", "debug")
    SYNC_TOKEN = response.next_batch


async def main():
    global MATRIX_CLIENT

    if not MATRIX_CLIENT.user_id:
        whoami = await MATRIX_CLIENT.whoami()
        MATRIX_CLIENT.user_id = whoami.user_id

    try:
        assert MATRIX_CLIENT.user_id
    except AssertionError:
        logging(
            "Failed to get user ID - check your access token or try setting it manually", "critical")
        await MATRIX_CLIENT.close()
        return

    logging("Starting bot...")

    MATRIX_CLIENT.add_response_callback(sync_cb, SyncResponse)

    logging("Syncing...")

    await MATRIX_CLIENT.sync(timeout=30000)

    MATRIX_CLIENT.add_event_callback(message_callback, RoomMessageText)
    MATRIX_CLIENT.add_event_callback(room_invite_callback, InviteEvent)

    await accept_pending_invites()  # Accept pending invites

    logging("Bot started")

    try:
        # Continue syncing events
        await MATRIX_CLIENT.sync_forever(timeout=30000)
    finally:
        logging("Syncing one last time...")
        await MATRIX_CLIENT.sync(timeout=30000)
        await MATRIX_CLIENT.close()  # Properly close the aiohttp client session
        logging("Bot stopped")


def initialize_database(path):
    global DATABASE

    logging("Initializing database...")
    DATABASE = duckdb.connect(path)

    with DATABASE.cursor() as cursor:
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

        DATABASE.commit()


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

    MATRIX_CLIENT = AsyncClient(config["Matrix"]["Homeserver"])

    MATRIX_CLIENT.access_token = config["Matrix"]["AccessToken"]
    MATRIX_CLIENT.user_id = config["Matrix"].get("UserID")

    # Set up GPT API
    try:
        assert "OpenAI" in config
        assert "APIKey" in config["OpenAI"]
    except:
        logging("OpenAI config not found or incomplete", "critical")
        exit(1)

    openai.api_key = config["OpenAI"]["APIKey"]

    if "Model" in config["OpenAI"]:
        DEFAULT_MODEL = config["OpenAI"]["Model"]

    if "MaxTokens" in config["OpenAI"]:
        MAX_TOKENS = int(config["OpenAI"]["MaxTokens"])

    if "MaxMessages" in config["OpenAI"]:
        MAX_MESSAGES = int(config["OpenAI"]["MaxMessages"])

    # Set up database
    if "Database" in config and config["Database"].get("Path"):
        initialize_database(config["Database"]["Path"])

    # Start bot loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging("Received KeyboardInterrupt - exiting...")
    except signal.SIGTERM:
        logging("Received SIGTERM - exiting...")
    finally:
        if DATABASE:
            DATABASE.close()
