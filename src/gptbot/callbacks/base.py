from ..classes.bot import GPTBot

from nio import Event

class BaseEventCallback:
    EVENTS = [] # List of events that this callback should be called for

    def __init__(self, bot: GPTBot):
        """Initialize the callback with the bot instance

        Args:
            bot (GPTBot): GPTBot instance
        """
        self.bot = bot

    async def process(self, event: Event, *args, **kwargs):
        raise NotImplementedError(
            "BaseEventCallback.process() must be implemented by subclasses"
        )

class BaseResponseCallback:
    RESPONSES = [] # List of responses that this callback should be called for

    def __init__(self, bot: GPTBot):
        """Initialize the callback with the bot instance

        Args:
            bot (GPTBot): GPTBot instance
        """
        self.bot = bot

    async def process(self, response: Response, *args, **kwargs):
        raise NotImplementedError(
            "BaseResponseCallback.process() must be implemented by subclasses"
        )
    