from .base import BaseTool

from datetime import datetime

class Datetime(BaseTool):
    DESCRIPTION = "Get the current date and time."
    PARAMETERS = {
        "type": "object",
        "properties": {
        },
    }

    async def run(self):
        """Get the current date and time."""
        return f"""**Current date and time (UTC)**
{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}"""