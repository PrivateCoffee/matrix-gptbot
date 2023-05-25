# Migration to add settings table

from datetime import datetime
from contextlib import closing

def migration(conn):
    with closing(conn.cursor()) as cursor:
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