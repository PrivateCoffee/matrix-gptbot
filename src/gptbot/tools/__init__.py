from importlib import import_module

from .base import BaseTool, StopProcessing, Handover

TOOLS = {}

for tool in [
    "weather",
    "geocode",
    "dice",
    "websearch",
    "webrequest",
    "imagine",
    "imagedescription",
    "wikipedia",
]:
    tool_class = getattr(import_module(
        "." + tool, "gptbot.tools"), tool.capitalize())
    TOOLS[tool] = tool_class
