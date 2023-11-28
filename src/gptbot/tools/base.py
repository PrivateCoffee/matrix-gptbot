class BaseTool:
    DESCRIPTION: str
    PARAMETERS: list

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.bot = kwargs["bot"]

    async def run(self):
        raise NotImplementedError()
