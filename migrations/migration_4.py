# Migration to add API column to token usage table

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE token_usage ADD COLUMN api TEXT DEFAULT 'openai'
            """
        )

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (4, ?)",
            (datetime.now(),)
        )

        conn.commit()