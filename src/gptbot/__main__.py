from .classes.bot import GPTBot

from argparse import ArgumentParser
from configparser import ConfigParser

import signal
import asyncio
import importlib.metadata

def sigterm_handler(_signo, _stack_frame):
    exit()

def get_version():
    try:
        package_version = importlib.metadata.version("matrix_gptbot")
    except pkg_resources.DistributionNotFound:
        return None
    return package_version

def main():
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
        version=f"GPTBot {get_version() or '- version unknown'}",
    )
    args = parser.parse_args()

    # Read config file
    config = ConfigParser()
    config.read(args.config)

    # Create bot
    bot, new_config = GPTBot.from_config(config)

    # Update config with new values
    if new_config:
        with open(args.config, "w") as configfile:
            new_config.write(configfile)

    # Listen for SIGTERM
    signal.signal(signal.SIGTERM, sigterm_handler)

    # Start bot
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt - exiting...")
    except SystemExit:
        print("Received SIGTERM - exiting...")


if __name__ == "__main__":
    main()