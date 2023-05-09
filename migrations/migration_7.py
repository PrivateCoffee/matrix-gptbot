# Migration to add user_spaces table

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE user_spaces (
                space_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (space_id, user_id)
            )
            """
        )

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (7, ?)",
            (datetime.now(),)
        )

        conn.commit()