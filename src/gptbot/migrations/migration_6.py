# Migration to drop primary key constraint from token_usage table

from datetime import datetime
from contextlib import closing

def migration(conn):
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            CREATE TABLE token_usage_temp (
                message_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                api TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            "INSERT INTO token_usage_temp SELECT message_id, room_id, api, tokens, timestamp FROM token_usage"
        )

        cursor.execute("DROP TABLE token_usage")

        cursor.execute("ALTER TABLE token_usage_temp RENAME TO token_usage")

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (6, ?)",
            (datetime.now(),)
        )

        conn.commit()