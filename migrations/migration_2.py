# Migration for Matrix Store

from datetime import datetime

def migration(conn):
    with conn.cursor() as cursor:
        # Create accounts table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            device_id VARCHAR NOT NULL,
            shared_account INTEGER NOT NULL,
            pickle VARCHAR NOT NULL
        );
        """)

        # Create device_keys table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_keys (
            device_id TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            display_name TEXT,
            deleted BOOLEAN NOT NULL DEFAULT 0,
            UNIQUE (account_id, user_id, device_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keys (
            key_type TEXT NOT NULL,
            key TEXT NOT NULL,
            device_id VARCHAR NOT NULL,
            UNIQUE (key_type, device_id),
            FOREIGN KEY (device_id) REFERENCES device_keys(device_id) ON DELETE CASCADE
        );
        """)

        # Create device_trust_state table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_trust_state (
            device_id VARCHAR PRIMARY KEY,
            state INTEGER NOT NULL,
            FOREIGN KEY(device_id) REFERENCES device_keys(device_id) ON DELETE CASCADE
        );
        """)

        # Create olm_sessions table
        cursor.execute("""
        CREATE SEQUENCE IF NOT EXISTS olm_sessions_id_seq START 1;

        CREATE TABLE IF NOT EXISTS olm_sessions (
            id INTEGER PRIMARY KEY DEFAULT nextval('olm_sessions_id_seq'),
            account_id INTEGER NOT NULL,
            sender_key TEXT NOT NULL,
            session BLOB NOT NULL,
            session_id VARCHAR NOT NULL,
            creation_time TIMESTAMP NOT NULL,
            last_usage_date TIMESTAMP NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
        );
        """)

        # Create inbound_group_sessions table
        cursor.execute("""
        CREATE SEQUENCE IF NOT EXISTS inbound_group_sessions_id_seq START 1;

        CREATE TABLE IF NOT EXISTS inbound_group_sessions (
            id INTEGER PRIMARY KEY DEFAULT nextval('inbound_group_sessions_id_seq'),
            account_id INTEGER NOT NULL,
            session TEXT NOT NULL,
            fp_key TEXT NOT NULL,
            sender_key TEXT NOT NULL,
            room_id TEXT NOT NULL,
            UNIQUE (account_id, sender_key, fp_key, room_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS forwarded_chains (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            sender_key TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES inbound_group_sessions(id) ON DELETE CASCADE
        );
        """)

        # Create outbound_group_sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS outbound_group_sessions (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            room_id VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL UNIQUE,
            session BLOB NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        """)

        # Create outgoing_key_requests table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS outgoing_key_requests (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            request_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (account_id, request_id)
        );

        """)

        # Create encrypted_rooms table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS encrypted_rooms (
            room_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            PRIMARY KEY (room_id, account_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        """)

        # Create sync_tokens table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_tokens (
            account_id INTEGER PRIMARY KEY,
            token TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        """)
        
        cursor.execute(
            "INSERT INTO migrations (id, timestamp) VALUES (2, ?)",
            (datetime.now(),)
        )

        conn.commit()