# GPTbot

GPTbot is a simple bot that uses different APIs to generate responses to 
messages in a Matrix room.

It is called GPTbot because it was originally intended to only use GPT-3 to
generate responses. However, it supports other services/APIs, and I will 
probably add more in the future, so the name is a bit misleading.

## Features

- AI-generated responses to messages in a Matrix room (chatbot)
  - Currently supports OpenAI (tested with `gpt-3.5-turbo` and `gpt-4`)
- AI-generated pictures via the `!gptbot imagine` command
  - Currently supports OpenAI (DALL-E)
- Mathematical calculations via the `!gptbot calculate` command
  - Currently supports WolframAlpha
- Automatic classification of messages (for `imagine`, `calculate`, etc.)
  - Beta feature, see Usage section for details
- Really useful commands like `!gptbot help` and `!gptbot coin`
- DuckDB database to store room context

## Planned features

- End-to-end encryption support (partly implemented, but not yet working)

## Installation

To run the bot, you will need Python 3.10 or newer. 

The bot has been tested with Python 3.11 on Arch, but should work with any 
current version, and should not require any special dependencies or operating
system features.

### Production

The easiest way to install the bot is to use pip to install it directly from
[its Git repository](https://kumig.it/kumitterer/matrix-gptbot/):

```shell
# If desired, activate a venv first

python -m venv venv
. venv/bin/activate

# Install the bot

pip install git+https://kumig.it/kumitterer/matrix-gptbot.git
```

This will install the bot from the main branch and all required dependencies.
A release to PyPI is planned, but not yet available.

### Development

Clone the repository and install the requirements to a virtual environment. 

```shell
# Clone the repository

git clone https://kumig.it/kumitterer/matrix-gptbot.git
cd matrix-gptbot

# If desired, activate a venv first

python -m venv venv
. venv/bin/activate

# Install the requirements

pip install -Ur requirements.txt

# Install the bot in editable mode

pip install -e .

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

### Commands

There are a few commands that you can use to interact with the bot. For example,
if you want to generate an image from a text prompt, you can use the
`!gptbot imagine` command. For example, `!gptbot imagine a cat` will cause the
bot to generate an image of a cat.

To learn more about the available commands, `!gptbot help` will print a list of
available commands.

### Automatic classification

As a beta feature, the bot can automatically classify messages and use the
appropriate API to generate a response. For example, if you send a message
like "Draw me a picture of a cat", the bot will automatically use the
`imagine` command to generate an image of a cat.

This feature is disabled by default. To enable it, use the `!gptbot roomsettings`
command to change the settings for the current room. `!gptbot roomsettings classification true`
will enable automatic classification, and `!gptbot roomsettings classification false`
will disable it again.

Note that this feature is still in beta and may not work as expected. You can
always use the commands manually if the automatic classification doesn't work
for you (including `!gptbot chat` for a regular chat message).

Also note that this feature conflicts with the `always_reply false` setting -
or rather, it doesn't make sense then because you already have to explicitly
specify the command to use.

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

This project is licensed under the terms of the MIT license. See the [LICENSE](LICENSE) file for details.
