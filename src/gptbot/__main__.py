from .classes.bot import GPTBot

from argparse import ArgumentParser
from configparser import ConfigParser

import signal
import asyncio


def sigterm_handler(_signo, _stack_frame):
    exit()


if __name__ == "__main__":
    # Parse command line arguments
    parser = ArgumentParser()
    parser.add_argument(
        "--config",
        "-c",
        help="Path to config file (default: config.ini in working directory)",
        default="config.ini",
    )
    parser.add_argument(
        "--version",
        "-v",
        help="Print version and exit",
        action="version",
        version="GPTBot v0.1.0",
    )
    args = parser.parse_args()

    # Read config file
    config = ConfigParser()
    config.read(args.config)

    # Create bot
    bot = GPTBot.from_config(config)

    # Listen for SIGTERM
    signal.signal(signal.SIGTERM, sigterm_handler)

    # Start bot
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt - exiting...")
    except SystemExit:
        print("Received SIGTERM - exiting...")
