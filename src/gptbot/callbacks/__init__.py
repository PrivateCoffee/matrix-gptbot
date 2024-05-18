from nio import (
    RoomMessageText,
    InviteEvent,
    SyncResponse,
    JoinResponse,
    RoomMemberEvent,
)

from .sync import sync_callback
from .invite import room_invite_callback
from .join import join_callback
from .message import message_callback
from .roommember import roommember_callback

RESPONSE_CALLBACKS = {
    SyncResponse: sync_callback,
    JoinResponse: join_callback,
}

EVENT_CALLBACKS = {
    InviteEvent: room_invite_callback,
    RoomMessageText: message_callback,
    RoomMemberEvent: roommember_callback,
}
