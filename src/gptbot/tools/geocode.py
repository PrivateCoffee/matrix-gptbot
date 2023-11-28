from geopy.geocoders import Nominatim

from .base import BaseTool

class Geocode(BaseTool):
    DESCRIPTION = "Get location information (latitude, longitude) for a given location name."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The location name.",
            },
        },
        "required": ["location"],
    }


    async def run(self):
        """Get location information for a given location."""
        if not (location := self.kwargs.get("location")):
            raise Exception('No location provided.')

        geolocator = Nominatim(user_agent=self.bot.USER_AGENT)

        location = geolocator.geocode(location)

        if location:
            return f"""**Location information for {location.address}**
Latitude: {location.latitude}
Longitude: {location.longitude}
"""

        raise Exception('Could not find location data for that location.')