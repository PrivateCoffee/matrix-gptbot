from .help import command_help
from .newroom import command_newroom
from .stats import command_stats
from .botinfo import command_botinfo
from .unknown import command_unknown
from .coin import command_coin
from .ignoreolder import command_ignoreolder

COMMANDS = {
    "help": command_help,
    "newroom": command_newroom,
    "stats": command_stats,
    "botinfo": command_botinfo,
    "coin": command_coin,
    "ignoreolder": command_ignoreolder,
    None: command_unknown,
}
