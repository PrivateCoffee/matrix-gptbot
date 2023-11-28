from .base import BaseTool

from random import SystemRandom

class Dice(BaseTool):
    DESCRIPTION = "Roll dice."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "dice": {
                "type": "string",
                "description": "The number of sides on the dice.",
                "default": "6",
            },
        },
        "required": [],
    }

    async def run(self):
        """Roll dice."""
        dice = int(self.kwargs.get("dice", 6))

        return f"""**Dice roll**
Used dice: {dice}
Result: {SystemRandom().randint(1, dice)}
"""