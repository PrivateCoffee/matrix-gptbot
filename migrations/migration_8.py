# Migration to add settings table

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                setting TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (setting)
            )
            """
        )

        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (8, ?)",
            (datetime.now(),)
        )

        conn.commit()