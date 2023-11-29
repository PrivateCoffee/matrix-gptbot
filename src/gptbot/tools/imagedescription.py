from .base import BaseTool, Handover

class Imagedescription(BaseTool):
    DESCRIPTION = "Describe the content of an image."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "image": {
                "type": "string",
                "description": "The image to describe.",
            },
        },
        "required": ["image"],
    }

    async def run(self):
        """Describe an image.
        
        This tool only hands over to the original model, if applicable.
        It is intended to handle the case where GPT-3 thinks it is asked to
        *generate* an image, but the user actually wants to *describe* an
        image...
        """
        raise Handover()