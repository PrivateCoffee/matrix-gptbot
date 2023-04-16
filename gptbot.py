import sqlite3
import os
import inspect

import openai
import asyncio
import markdown2
import tiktoken

from nio import AsyncClient, RoomMessageText, MatrixRoom, Event, InviteEvent
from nio.api import MessageDirection
from nio.responses import RoomMessagesError, SyncResponse

from configparser import ConfigParser
from datetime import datetime

config = ConfigParser()
config.read("config.ini")

# Set up GPT API
openai.api_key = config["OpenAI"]["APIKey"]
MODEL = config["OpenAI"].get("Model", "gpt-3.5-turbo")

# Set up Matrix client
MATRIX_HOMESERVER = config["Matrix"]["Homeserver"]
MATRIX_ACCESS_TOKEN = config["Matrix"]["AccessToken"]
BOT_USER_ID = config["Matrix"]["UserID"]

client = AsyncClient(MATRIX_HOMESERVER, BOT_USER_ID)

SYNC_TOKEN = None

# Set up SQLite3 database
conn = sqlite3.connect("token_usage.db")
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS token_usage (
        room_id TEXT NOT NULL,
        tokens INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)
conn.commit()

# Define the system message and max token limit
SYSTEM_MESSAGE = "You are a helpful assistant."
MAX_TOKENS = 3000


def logging(message, log_level="info"):
    caller = inspect.currentframe().f_back.f_code.co_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
    print(f"[{timestamp} - {caller}] [{log_level.upper()}] {message}")


async def gpt_query(messages):
    logging(f"Querying GPT with {len(messages)} messages")
    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages
        )
        result_text = response.choices[0].message['content']
        tokens_used = response.usage["total_tokens"]
        logging(f"Used {tokens_used} tokens")
        return result_text, tokens_used

    except Exception as e:
        logging(f"Error during GPT API call: {e}", "error")
        return None, 0


async def fetch_last_n_messages(room_id, n=20):
    # Fetch the last n messages from the room
    room = await client.join(room_id)
    messages = []

    logging(f"Fetching last {n} messages from room {room_id} (starting at {SYNC_TOKEN})...")

    response = await client.room_messages(
        room_id=room_id,
        start=SYNC_TOKEN,
        limit=n,
    )

    if isinstance(response, RoomMessagesError):
        logging(
            f"Error fetching messages: {response.message} (status code {response.status_code})", "error")
        return []

    for event in response.chunk:
        if isinstance(event, RoomMessageText):
            messages.append(event)

    logging(f"Found {len(messages)} messages")

    # Reverse the list so that messages are in chronological order
    return messages[::-1]


def truncate_messages_to_fit_tokens(messages, max_tokens=MAX_TOKENS):
    encoding = tiktoken.encoding_for_model(MODEL)
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


async def message_callback(room: MatrixRoom, event: RoomMessageText):
    logging(f"Received message from {event.sender} in room {room.room_id}")

    if event.sender == BOT_USER_ID:
        logging("Message is from bot - ignoring")
        return

    await client.room_typing(room.room_id, True)

    await client.room_read_markers(room.room_id, event.event_id)

    last_messages = await fetch_last_n_messages(room.room_id, 20)

    if not last_messages or all(message.sender == BOT_USER_ID for message in last_messages):
        logging("No messages to respond to")
        await client.room_typing(room.room_id, False)
        return

    chat_messages = [{"role": "system", "content": SYSTEM_MESSAGE}]

    for message in last_messages:
        role = "assistant" if message.sender == BOT_USER_ID else "user"
        if not message.event_id == event.event_id:
            chat_messages.append({"role": role, "content": message.body})

    chat_messages.append({"role": "user", "content": event.body})

    # Truncate messages to fit within the token limit
    truncated_messages = truncate_messages_to_fit_tokens(
        chat_messages, MAX_TOKENS - 1)

    response, tokens_used = await gpt_query(truncated_messages)

    if response:
        # Send the response to the room

        logging(f"Sending response to room {room.room_id}...")

        markdowner = markdown2.Markdown(extras=["fenced-code-blocks"])
        formatted_body = markdowner.convert(response)

        await client.room_send(
            room.room_id, "m.room.message", {"msgtype": "m.text", "body": response,
                                             "format": "org.matrix.custom.html", "formatted_body": formatted_body}
        )

        logging("Logging tokens used...")

        cursor.execute(
            "INSERT INTO token_usage (room_id, tokens) VALUES (?, ?)", (room.room_id, tokens_used))
        conn.commit()
    else:
        # Send a notice to the room if there was an error

        logging("Error during GPT API call - sending notice to room")

        await client.room_send(
            room.room_id, "m.room.message", {
                "msgtype": "m.notice", "body": "Sorry, I'm having trouble connecting to the GPT API right now. Please try again later."}
        )
        print("No response from GPT API")

    await client.room_typing(room.room_id, False)


async def room_invite_callback(room: MatrixRoom, event):
    logging(f"Received invite to room {room.room_id} - joining...")

    await client.join(room.room_id)
    await client.room_send(
        room.room_id,
        "m.room.message",
        {"msgtype": "m.text",
            "body": "Hello! I'm a helpful assistant. How can I help you today?"}
    )


async def accept_pending_invites():
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


async def sync_cb(response):
    global SYNC_TOKEN
    logging(f"Sync response received (next batch: {response.next_batch})")
    SYNC_TOKEN = response.next_batch


async def main():
    logging("Starting bot...")

    client.access_token = MATRIX_ACCESS_TOKEN  # Set the access token directly
    client.user_id = BOT_USER_ID  # Set the user_id directly

    client.add_response_callback(sync_cb, SyncResponse)

    logging("Syncing...")

    await client.sync(timeout=30000)

    client.add_event_callback(message_callback, RoomMessageText)
    client.add_event_callback(room_invite_callback, InviteEvent)

    await accept_pending_invites()  # Accept pending invites

    logging("Bot started")

    try:
        await client.sync_forever(timeout=30000)  # Continue syncing events
    finally:
        await client.close()  # Properly close the aiohttp client session
        logging("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        conn.close()
