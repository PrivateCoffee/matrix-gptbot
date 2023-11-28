from .base import BaseTool

import aiohttp

from bs4 import BeautifulSoup

import re

class Webrequest(BaseTool):
    DESCRIPTION = "Browse an external website by URL."
    PARAMETERS = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request.",
            },
        },
        "required": ["url"],
    }

    async def html_to_text(self, html):
        # Parse the HTML content of the response
        soup = BeautifulSoup(html, 'html.parser')

        # Format the links within the text
        for link in soup.find_all('a'):
            link_text = link.get_text()
            link_href = link.get('href')
            new_link_text = f"{link_text} ({link_href})"
            link.replace_with(new_link_text)

        # Extract the plain text content of the website
        plain_text_content = soup.get_text()

        # Remove extra whitespace
        plain_text_content = re.sub('\s+', ' ', plain_text_content).strip()

        # Return the formatted text content of the website
        return plain_text_content

    async def run(self):
        """Make a web request to a given URL."""
        if not (url := self.kwargs.get("url")):
            raise Exception('No URL provided.')

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()

                    output = await self.html_to_text(data)

                    return f"""**Web request**
URL: {url}
Status: {response.status} {response.reason}

{output}
"""