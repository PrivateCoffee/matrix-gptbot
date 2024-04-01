# GPTbot

GPTbot is a simple bot that uses different APIs to generate responses to
messages in a Matrix room.

## Features

- AI-generated responses to text, image and voice messages in a Matrix room 
(chatbot)
  - Currently supports OpenAI (`gpt-3.5-turbo` and `gpt-4`, including vision 
  preview, `whisper` and `tts`)
  - Able to generate pictures using OpenAI `dall-e-2`/`dall-e-3` models
  - Able to browse the web to find information
  - Able to use OpenWeatherMap to get weather information (requires separate 
  API key)
  - Even able to roll dice!
- Mathematical calculations via the `!gptbot calculate` command
  - Currently supports WolframAlpha (requires separate API key)
- Really useful commands like `!gptbot help` and `!gptbot coin`
- sqlite3 database to store room settings

## Installation

To run the bot, you will need Python 3.10 or newer.

The bot has been tested with Python 3.11 on Arch, but should work with any
current version, and should not require any special dependencies or operating
system features.

### Production

The easiest way to install the bot is to use pip to install it from pypi.

```shell
# If desired, activate a venv first

python -m venv venv
. venv/bin/activate

# Install the bot

pip install matrix-gptbot[all]
```

This will install the latest release of the bot and all required dependencies
for all available features.

You can also use `pip install git+https://git.private.coffee/kumi/matrix-gptbot.git`
to install the latest version from the Git repository.

#### End-to-end encryption

WARNING: Using end-to-end encryption seems to sometimes cause problems with
file attachments, especially in rooms that are not encrypted, if the same
user also uses the bot in encrypted rooms.

The bot itself does not implement end-to-end encryption. However, it can be
used in conjunction with [pantalaimon](https://github.com/matrix-org/pantalaimon),
which is actually installed as a dependency of the bot.

To use pantalaimon, create a `pantalaimon.conf` following the example in
`pantalaimon.example.conf`, making sure to change the homeserver URL to match
your homeserver. Then, start pantalaimon with `pantalaimon -c pantalaimon.conf`.

You first have to log in to your homeserver using `python pantalaimon_first_login.py`,
and can then use the returned access token in your bot's `config.ini` file.

Make sure to also point the bot to your pantalaimon instance by setting 
`homeserver` to your pantalaimon instance instead of directly to your 
homeserver in your `config.ini`.

Note: If you don't use pantalaimon, the bot will still work, but it will not 
be able to decrypt or encrypt messages. This means that you cannot use it in
rooms with end-to-end encryption enabled.

### Development

Clone the repository and install the requirements to a virtual environment.

```shell
# Clone the repository

git clone https://git.private.coffee/kumi/matrix-gptbot.git
cd matrix-gptbot

# If desired, activate a venv first

python -m venv venv
. venv/bin/activate

# Install the bot in editable mode

pip install -e .[dev]

# Go to the bot directory and start working

cd src/gptbot
```

Of course, you can also fork the repository on [GitHub](https://github.com/kumitterer/matrix-gptbot/)
and work on your own copy.

### Configuration

The bot requires a configuration file to be present in the working directory.
Copy the provided `config.dist.ini` to `config.ini` and edit it to your needs.

## Running

The bot can be run with `python -m gptbot`. If required, activate a venv first.

You may want to run the bot in a screen or tmux session, or use a process
manager like systemd. The repository contains a sample systemd service file
(`gptbot.service`) that you can use as a starting point. You will need to
adjust the paths in the file to match your setup, then copy it to
`/etc/systemd/system/gptbot.service`. You can then start the bot with
`systemctl start gptbot` and enable it to start automatically on boot with
`systemctl enable gptbot`.

Analogously, you can use the provided `gptbot-pantalaimon.service` file to run
pantalaimon as a systemd service.

## Usage

Once it is running, just invite the bot to a room and it will start responding
to messages. If you want to create a new room, you can use the `!gptbot newroom`
command at any time, which will cause the bot to create a new room and invite
you to it. You may also specify a room name, e.g. `!gptbot newroom My new room`.

### Reply generation

Note that the bot will respond to _all_ messages in the room by default. If you
don't want this, for example because you want to use the bot in a room with
other people, you can use the `!gptbot roomsettings` command to change the
settings for the current room. For example, you can disable response generation
with `!gptbot roomsettings always_reply false`.

With this setting, the bot will only be triggered if a message begins with
`!gptbot chat`. For example, `!gptbot chat Hello, how are you?` will cause the
bot to generate a response to the message `Hello, how are you?`. The bot will
still get previous messages in the room as context for generating the response.

### Tools

The bot has a selection of tools at its disposal that it will automatically use
to generate responses. For example, if you send a message like "Draw me a
picture of a cat", the bot will automatically use DALL-E to generate an image
of a cat.

Note that this only works if the bot is configured to use a model that supports
tools. This currently is only the case for OpenAI's `gpt-3.5-turbo` model. If
you wish to use `gpt-4` instead, you can set the `ForceTools` option in the 
`[OpenAI]` section of the config file to `1`. This will cause the bot to use
`gpt-3.5-turbo` for tool generation and `gpt-4` for generating the final text
response.

Similarly, it will attempt to use the `gpt-4-vision-preview` model to "read" 
the contents of images if a non-vision model is used.

### Commands

There are a few commands that you can use to explicitly call a certain feature
of the bot. For example, if you want to generate an image from a text prompt, 
you can use the `!gptbot imagine` command. For example, `!gptbot imagine a cat`
will cause the bot to generate an image of a cat.

To learn more about the available commands, `!gptbot help` will print a list of
available commands.

### Voice input and output

The bot supports voice input and output, but it is disabled by default. To
enable it, use the `!gptbot roomsettings` command to change the settings for
the current room. `!gptbot roomsettings stt true` will enable voice input using
OpenAI's `whisper` model, and `!gptbot roomsettings tts true` will enable voice
output using the `tts` model.

Note that this currently only works for audio messages and .mp3 file uploads.

## Troubleshooting

**Help, the bot is not responding!**

First of all, make sure that the bot is actually running. (Okay, that's not
really troubleshooting, but it's a good start.)

If the bot is running, check the logs. The first few lines should contain
"Starting bot...", "Syncing..." and "Bot started". If you don't see these
lines, something went wrong during startup. Fortunately, the logs should
contain more information about what went wrong.

If you need help figuring out what went wrong, feel free to open an issue.

**Help, the bot is flooding the room with responses!**

The bot will respond to _all_ messages in the room, with two exceptions:

- If you turn off response generation for the room, the bot will only respond
  to messages that begin with `!gptbot <command>`.
- Messages sent by the bot itself will not trigger a response.

There is a good chance that you are seeing the bot responding to its own
messages. First, stop the bot, or it will keep responding to its own messages,
consuming tokens.

Check that the UserID provided in the config file matches the UserID of the bot.
If it doesn't, change the config file and restart the bot. Note that the UserID
is optional, so you can also remove it from the config file altogether and the
bot will try to figure out its own User ID.

If the User ID is correct or not set, something else is going on. In this case,
please check the logs and open an issue if you can't figure out what's going on.

## License

This project is licensed under the terms of the MIT license. See the [LICENSE](LICENSE)
file for details.
