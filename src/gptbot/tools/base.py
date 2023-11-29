class BaseTool:
    DESCRIPTION: str
    PARAMETERS: dict

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.bot = kwargs["bot"]
        self.room = kwargs["room"]
        self.user = kwargs["user"]

    async def run(self):
        raise NotImplementedError()

class StopProcessing(Exception):
    """Stop processing the message."""
    pass

class Handover(Exception):
    """Handover to the original model, if applicable. Stop using tools."""
    pass