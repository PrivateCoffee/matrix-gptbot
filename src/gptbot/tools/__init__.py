from importlib import import_module

TOOLS = {}

for tool in [
    "weather",
    "geocode",
    "dice",
    "websearch",
    "webrequest",
]:
    tool_class = getattr(import_module(
        "." + tool, "gptbot.tools"), tool.capitalize())
    TOOLS[tool] = tool_class
