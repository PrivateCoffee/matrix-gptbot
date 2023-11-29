from .base import BaseTool

from urllib.parse import urlencode

import aiohttp

class Wikipedia(BaseTool):
    DESCRIPTION = "Get information from Wikipedia."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for.",
            },
            "language": {
                "type": "string",
                "description": "The language to search in.",
                "default": "en",
            },
        },
        "required": ["query"],
    }

    async def run(self):
        """Get information from Wikipedia."""
        if not (query := self.kwargs.get("query")):
            raise Exception('No query provided.')

        language = self.kwargs.get("language", "en")
        extract = self.kwargs.get("extract", False)

        args = {
            "action": "query",
            "format": "json",
            "titles": query,
        }

        if extract:
            args["prop"] = "extracts"
            args["exintro"] = ""

        else:
            args["prop"] = "revisions"
            args["rvprop"] = "content"

        url = f'https://{language}.wikipedia.org/w/api.php?{urlencode(args)}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pages = data['query']['pages']
                    page = list(pages.values())[0]
                    if 'extract' in page:
                        return f"**{page['title']} (Extract)**\n{page['extract']}"
                    elif 'revisions' in page:
                        return f"**{page['title']}**\n{page['revisions'][0]['*']}"
                    else:
                        raise Exception('No results found.')
                else:
                    raise Exception(f'Could not connect to Wikipedia API: {response.status} {response.reason}')