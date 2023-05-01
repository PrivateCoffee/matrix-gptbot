from importlib import import_module

from .unknown import command_unknown

COMMANDS = {}

for command in [
    "help",
    "newroom",
    "stats",
    "botinfo",
    "coin",
    "ignoreolder",
    "systemmessage",
    "imagine",
    "calculate",
    "classify",
    "chat",
    "custom",
    "privacy",
    "roomsettings",
    "dice",
]:
    function = getattr(import_module(
        "commands." + command), "command_" + command)
    COMMANDS[command] = function

COMMANDS[None] = command_unknown
