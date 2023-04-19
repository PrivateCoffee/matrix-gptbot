from nio.events.room_events import RoomMessageText
from nio.rooms import MatrixRoom

async def command_newroom(room: MatrixRoom, event: RoomMessageText, context: dict):
    room_name = " ".join(event.body.split()[2:]) or context["default_room_name"]

    context["logger"]("Creating new room...")
    new_room = await context["client"].room_create(name=room_name)

    context["logger"](f"Inviting {event.sender} to new room...")
    await context["client"].room_invite(new_room.room_id, event.sender)
    await context["client"].room_put_state(
        new_room.room_id, "m.room.power_levels", {"users": {event.sender: 100}})

    await context["client"].room_send(
        new_room.room_id, "m.room.message", {"msgtype": "m.text", "body": "Welcome to the new room!"})
