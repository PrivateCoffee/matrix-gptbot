from .base import BaseTool

import aiohttp

from urllib.parse import quote_plus

class Websearch(BaseTool):
    DESCRIPTION = "Search the web for a given query."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for.",
            },
        },
        "required": ["query"],
    }

    async def run(self):
        """Search the web for a given query."""
        if not (query := self.kwargs.get("query")):
            raise Exception('No query provided.')

        query = quote_plus(query)

        url = f'https://librey.private.coffee/api.php?q={query}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    response_text = "**Search results for {query}**"
                    for result in data:
                        response_text += f"\n{result['title']}\n{result['url']}\n{result['description']}\n"
                    
                    return response_text