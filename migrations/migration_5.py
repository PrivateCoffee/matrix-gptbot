# Migration to add room settings table

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS room_settings (
                room_id TEXT NOT NULL,
                setting TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (room_id, setting)
            )
            """
        )

        cursor.execute("SELECT * FROM system_messages")
        system_messages = cursor.fetchall()

        # Get latest system message for each room

        cursor.execute(
            """
            SELECT system_messages.room_id, system_messages.message_id, system_messages.user_id, system_messages.body, system_messages.timestamp
            FROM system_messages
            INNER JOIN (
                SELECT room_id, MAX(timestamp) AS timestamp FROM system_messages GROUP BY room_id
            ) AS latest_system_message ON system_messages.room_id = latest_system_message.room_id AND system_messages.timestamp = latest_system_message.timestamp
            """
        )

        system_messages = cursor.fetchall()

        for message in system_messages:
            cursor.execute(
                "INSERT INTO room_settings (room_id, setting, value) VALUES (?, ?, ?)",
                (message[0], "system_message", message[1])
            )

        cursor.execute("DROP TABLE system_messages")

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (5, ?)",
            (datetime.now(),)
        )

        conn.commit()