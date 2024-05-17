from .base import BaseTool

class Imagedescription(BaseTool):
    DESCRIPTION = "Describe the content of the images in the conversation."
    PARAMETERS = {
        "type": "object",
        "properties": {
        },
    }

    async def run(self):
        """Describe images in the conversation."""
        image_api = self.bot.image_api

        return (await image_api.describe_images(self.messages, self.user))[0]