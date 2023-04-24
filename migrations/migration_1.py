# Initial migration, token usage logging

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                message_id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (1, ?)",
            (datetime.now(),)
        )

        conn.commit()