from nio import (
    RoomMessageText,
    MegolmEvent,
    InviteEvent,
    Event,
    SyncResponse,
    JoinResponse,
    InviteEvent,
    OlmEvent,
    MegolmEvent,
    RoomMemberEvent,
    Response,
)

from .test import test_callback
from .sync import sync_callback
from .invite import room_invite_callback
from .join import join_callback
from .message import message_callback
from .roommember import roommember_callback
from .test_response import test_response_callback

RESPONSE_CALLBACKS = {
    Response: test_response_callback,
    SyncResponse: sync_callback,
    JoinResponse: join_callback,
}

EVENT_CALLBACKS = {
    Event: test_callback,
    InviteEvent: room_invite_callback,
    RoomMessageText: message_callback,
    MegolmEvent: message_callback,
    RoomMemberEvent: roommember_callback,
}