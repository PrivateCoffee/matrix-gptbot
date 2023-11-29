class BaseTool:
    DESCRIPTION: str
    PARAMETERS: dict

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.bot = kwargs.get("bot")
        self.room = kwargs.get("room")
        self.user = kwargs.get("user")
        self.messages = kwargs.get("messages", [])

    async def run(self):
        raise NotImplementedError()

class StopProcessing(Exception):
    """Stop processing the message."""
    pass

class Handover(Exception):
    """Handover to the original model, if applicable. Stop using tools."""
    pass