from .base import BaseTool, StopProcessing

class Imagine(BaseTool):
    DESCRIPTION = "Use generative AI to create images from text prompts."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The prompt to use.",
            },
            "orientation": {
                "type": "string",
                "description": "The orientation of the image.",
                "enum": ["square", "landscape", "portrait"],
                "default": "square",
            },
        },
        "required": ["prompt"],
    }

    async def run(self):
        """Use generative AI to create images from text prompts."""
        if not (prompt := self.kwargs.get("prompt")):
            raise Exception('No prompt provided.')

        api = self.bot.image_api
        orientation = self.kwargs.get("orientation", "square")
        images, tokens = await api.generate_image(prompt, self.room, orientation=orientation)

        for image in images:
            await self.bot.send_image(self.room, image, prompt)

        raise StopProcessing()