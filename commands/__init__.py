from .help import command_help
from .newroom import command_newroom
from .stats import command_stats
from .botinfo import command_botinfo
from .unknown import command_unknown
from .coin import command_coin
from .ignoreolder import command_ignoreolder
from .systemmessage import command_systemmessage
from .imagine import command_imagine
from .calculate import command_calculate
from .classify import command_classify
from .chat import command_chat

COMMANDS = {
    "help": command_help,
    "newroom": command_newroom,
    "stats": command_stats,
    "botinfo": command_botinfo,
    "coin": command_coin,
    "ignoreolder": command_ignoreolder,
    "systemmessage": command_systemmessage,
    "imagine": command_imagine,
    "calculate": command_calculate,
    "classify": command_classify,
    "chat": command_chat,
    None: command_unknown,
}
