# GPTbot

GPTbot is a simple bot that uses the [OpenAI ChatCompletion API](https://platform.openai.com/docs/guides/chat)
to generate responses to messages in a Matrix room.

It will also save a log of the spent tokens to a sqlite database
(token_usage.db in the working directory).

## Installation

Simply clone this repository and install the requirements.

### Requirements

* Python 3.8 or later
* Requirements from `requirements.txt` (install with `pip install -r requirements.txt` in a venv)

### Configuration

The bot requires a configuration file to be present in the working directory.
Copy the provided `config.dist.ini` to `config.ini` and edit it to your needs.

## Running

The bot can be run with `python -m gptbot`. If required, activate a venv first.

You may want to run the bot in a screen or tmux session, or use a process 
manager like systemd.

Once it is running, just invite it to a room and it will start responding to
messages.

## License

This project is licensed under the terms of the MIT license.