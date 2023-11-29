from .base import BaseTool, StopProcessing

from nio import RoomCreateError, RoomInviteError

from contextlib import closing

class Newroom(BaseTool):
    DESCRIPTION = "Create a new Matrix room"
    PARAMETERS = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the room to create.",
                "default": "GPTBot"
            }
        },   
    }

    async def run(self):
        """Create a new Matrix room"""
        name = self.kwargs.get("name", "GPTBot")

        self.bot.logger.log("Creating new room...")
        new_room = await self.bot.matrix_client.room_create(name=name)

        if isinstance(new_room, RoomCreateError):
            self.bot.logger.log(f"Failed to create room: {new_room.message}")
            raise

        self.bot.logger.log(f"Inviting {self.user} to new room...")
        invite = await self.bot.matrix_client.room_invite(new_room.room_id, self.user)

        if isinstance(invite, RoomInviteError):
            self.bot.logger.log(f"Failed to invite user: {invite.message}")
            raise

        await self.bot.send_message(new_room.room_id, "Welcome to your new room! What can I do for you?")

        with closing(self.bot.database.cursor()) as cursor:
            cursor.execute(
                "SELECT space_id FROM user_spaces WHERE user_id = ? AND active = TRUE", (event.sender,))
            space = cursor.fetchone()

        if space:
            self.bot.logger.log(f"Adding new room to space {space[0]}...")
            await self.bot.add_rooms_to_space(space[0], [new_room.room_id])

        if self.bot.logo_uri:
            await self.bot.matrix_client.room_put_state(room, "m.room.avatar", {
                "url": self.bot.logo_uri
            }, "")

        await self.bot.matrix_client.room_put_state(
            new_room.room_id, "m.room.power_levels", {"users": {self.user: 100, self.bot.matrix_client.user_id: 100}})

        raise StopProcessing("Created new Matrix room with ID " + new_room.room_id + " and invited user.")