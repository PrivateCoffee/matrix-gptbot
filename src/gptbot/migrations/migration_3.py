# Migration for custom system messages

from datetime import datetime
from contextlib import closing

def migration(conn):
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_messages (
                room_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp BIGINT NOT NULL
            )
            """
        )

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (3, ?)",
            (datetime.now(),)
        )

        conn.commit()