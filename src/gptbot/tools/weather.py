import aiohttp

from datetime import datetime

from .base import BaseTool

class Weather(BaseTool):
    DESCRIPTION = "Get weather information for a given location."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "string",
                "description": "The latitude of the location.",
            },
            "longitude": {
                "type": "string",
                "description": "The longitude of the location.",
            },
        },
        "required": ["latitude", "longitude"],
    }

    async def run(self):
        """Get weather information for a given location."""
        if not (latitude := self.kwargs.get("latitude")) or not (longitude := self.kwargs.get("longitude")):
            raise Exception('No location provided.')

        weather_api_key = self.bot.config.get("OpenWeatherMap", "APIKey")

        if not weather_api_key:
            raise Exception('Weather API key not found.')

        url = f'https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&appid={weather_api_key}&units=metric'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return f"""**Weather report**
Current: {data['current']['temp']}°C, {data['current']['weather'][0]['description']}
Feels like: {data['current']['feels_like']}°C
Humidity: {data['current']['humidity']}%
Wind: {data['current']['wind_speed']}m/s
Sunrise: {datetime.fromtimestamp(data['current']['sunrise']).strftime('%H:%M')}
Sunset: {datetime.fromtimestamp(data['current']['sunset']).strftime('%H:%M')}

Today: {data['daily'][0]['temp']['day']}°C, {data['daily'][0]['weather'][0]['description']}, {data['daily'][0]['summary']}
Tomorrow: {data['daily'][1]['temp']['day']}°C, {data['daily'][1]['weather'][0]['description']}, {data['daily'][1]['summary']}
"""
                else:
                    raise Exception(f'Could not connect to weather API: {response.status} {response.reason}')
