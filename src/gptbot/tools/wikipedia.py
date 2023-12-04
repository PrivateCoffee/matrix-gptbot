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
            "extract": {
                "type": "string",
                "description": "What information to extract from the page. If not provided, the full page will be returned."
            },
            "summarize": {
                "type": "boolean",
                "description": "Whether to summarize the page or not.",
                "default": False,
            }
        },
        "required": ["query"],
    }

    async def run(self):
        """Get information from Wikipedia."""
        if not (query := self.kwargs.get("query")):
            raise Exception('No query provided.')

        language = self.kwargs.get("language", "en")
        extract = self.kwargs.get("extract")
        summarize = self.kwargs.get("summarize", False)

        args = {
            "action": "query",
            "format": "json",
            "titles": query,
        }

        args["prop"] = "revisions"
        args["rvprop"] = "content"

        url = f'https://{language}.wikipedia.org/w/api.php?{urlencode(args)}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    try:
                        pages = data['query']['pages']
                        page = list(pages.values())[0]
                        content = page['revisions'][0]['*']
                    except KeyError:
                        raise Exception(f'No results for {query} found in Wikipedia.')

                    if extract:
                        chat_messages = [{"role": "system", "content": f"Extract the following from the provided content: {extract}"}]
                        chat_messages.append({"role": "user", "content": content})
                        content, _ = await self.bot.chat_api.generate_chat_response(chat_messages, room=self.room, user=self.user, allow_override=False, use_tools=False)

                    if summarize:
                        chat_messages = [{"role": "system", "content": "Summarize the following content:"}]
                        chat_messages.append({"role": "user", "content": content})
                        content, _ = await self.bot.chat_api.generate_chat_response(chat_messages, room=self.room, user=self.user, allow_override=False, use_tools=False)

                    return f"**Wikipedia: {page['title']}**\n{content}"

                else:
                    raise Exception(f'Could not connect to Wikipedia API: {response.status} {response.reason}')