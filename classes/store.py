import duckdb

from nio.store.database import MatrixStore, DeviceTrustState, OlmDevice, TrustState, InboundGroupSession, SessionStore, OlmSessions, GroupSessionStore, OutgoingKeyRequest, DeviceStore, Session
from nio.crypto import OlmAccount, OlmDevice

from random import SystemRandom
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .dict import AttrDict

import json


class DuckDBStore(MatrixStore):
    @property
    def account_id(self):
        id = self._get_account()[0] if self._get_account() else None

        if id is None:
            id = SystemRandom().randint(0, 2**16)

        return id

    def __init__(self, user_id, device_id, duckdb_conn):
        self.conn = duckdb_conn
        self.user_id = user_id
        self.device_id = device_id

    def _get_account(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND device_id = ?",
            (self.user_id, self.device_id),
        )
        account = cursor.fetchone()
        cursor.close()
        return account

    def _get_device(self, device):
        acc = self._get_account()

        if not acc:
            return None

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM device_keys WHERE user_id = ? AND device_id = ? AND account_id = ?",
            (device.user_id, device.id, acc[0]),
        )
        device_entry = cursor.fetchone()
        cursor.close()

        return device_entry

    # Implementing methods with DuckDB equivalents
    def verify_device(self, device):
        if self.is_device_verified(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], TrustState.verified),
        )
        self.conn.commit()
        cursor.close()

        device.trust_state = TrustState.verified

        return True

    def unverify_device(self, device):
        if not self.is_device_verified(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], TrustState.unset),
        )
        self.conn.commit()
        cursor.close()

        device.trust_state = TrustState.unset

        return True

    def is_device_verified(self, device):
        d = self._get_device(device)

        if not d:
            return False

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT state FROM device_trust_state WHERE device_id = ?", (d[0],)
        )
        trust_state = cursor.fetchone()
        cursor.close()

        if not trust_state:
            return False

        return trust_state[0] == TrustState.verified

    def blacklist_device(self, device):
        if self.is_device_blacklisted(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], TrustState.blacklisted),
        )
        self.conn.commit()
        cursor.close()

        device.trust_state = TrustState.blacklisted

        return True

    def unblacklist_device(self, device):
        if not self.is_device_blacklisted(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], TrustState.unset),
        )
        self.conn.commit()
        cursor.close()

        device.trust_state = TrustState.unset

        return True

    def is_device_blacklisted(self, device):
        d = self._get_device(device)

        if not d:
            return False

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT state FROM device_trust_state WHERE device_id = ?", (d[0],)
        )
        trust_state = cursor.fetchone()
        cursor.close()

        if not trust_state:
            return False

        return trust_state[0] == TrustState.blacklisted

    def ignore_device(self, device):
        if self.is_device_ignored(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], int(TrustState.ignored.value)),
        )
        self.conn.commit()
        cursor.close()

        return True

    def ignore_devices(self, devices):
        for device in devices:
            self.ignore_device(device)

    def unignore_device(self, device):
        if not self.is_device_ignored(device):
            return False

        d = self._get_device(device)
        assert d

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO device_trust_state (device_id, state) VALUES (?, ?)",
            (d[0], TrustState.unset),
        )
        self.conn.commit()
        cursor.close()

        device.trust_state = TrustState.unset

        return True

    def is_device_ignored(self, device):
        d = self._get_device(device)

        if not d:
            return False

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT state FROM device_trust_state WHERE device_id = ?", (d[0],)
        )
        trust_state = cursor.fetchone()
        cursor.close()

        if not trust_state:
            return False

        return trust_state[0] == TrustState.ignored

    def load_device_keys(self):
        """Load all the device keys from the database.

        Returns DeviceStore containing the OlmDevices with the device keys.
        """
        store = DeviceStore()
        account = self.account_id

        if not account:
            return store

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM device_keys WHERE account_id = ?",
                (account,)
            )
            device_keys = cur.fetchall()

            for d in device_keys:
                cur.execute(
                    "SELECT * FROM keys WHERE device_id = ?",
                    (d[0],)
                )
                keys = cur.fetchall()
                key_dict = {k[0]: k[1] for k in keys}

                store.add(
                    OlmDevice(
                        d[2],
                        d[0],
                        key_dict,
                        display_name=d[3],
                        deleted=d[4],
                    )
                )

        return store

    def save_device_keys(self, device_keys):
        """Save the provided device keys to the database."""
        account = self.account_id
        assert account
        rows = []

        for user_id, devices_dict in device_keys.items():
            for device_id, device in devices_dict.items():
                rows.append(
                    {
                        "account_id": account,
                        "user_id": user_id,
                        "device_id": device_id,
                        "display_name": device.display_name,
                        "deleted": device.deleted,
                    }
                )

        if not rows:
            return

        with self.conn.cursor() as cur:
            for idx in range(0, len(rows), 100):
                data = rows[idx: idx + 100]
                cur.executemany(
                    "INSERT OR IGNORE INTO device_keys (account_id, user_id, device_id, display_name, deleted) VALUES (?, ?, ?, ?, ?)",
                    [(r["account_id"], r["user_id"], r["device_id"],
                      r["display_name"], r["deleted"]) for r in data]
                )

            for user_id, devices_dict in device_keys.items():
                for device_id, device in devices_dict.items():
                    cur.execute(
                        "UPDATE device_keys SET deleted = ? WHERE device_id = ?",
                        (device.deleted, device_id)
                    )

                    for key_type, key in device.keys.items():
                        cur.execute("""
                            INSERT INTO keys (key_type, key, device_id) VALUES (?, ?, ?)
                            ON CONFLICT (key_type, device_id) DO UPDATE SET key = ?
                            """,
                                    (key_type, key, device_id, key)
                                    )
            self.conn.commit()

    def save_group_sessions(self, sessions):
        with self.conn.cursor() as cur:
            for session in sessions:
                cur.execute("""
                    INSERT OR REPLACE INTO inbound_group_sessions (
                        session_id, sender_key, signing_key, room_id, pickle, account_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session.id,
                    session.sender_key,
                    session.signing_key,
                    session.room_id,
                    session.pickle,
                    self.account_id
                ))

            self.conn.commit()

    def save_olm_sessions(self, sessions):
        with self.conn.cursor() as cur:
            for session in sessions:
                cur.execute("""
                    INSERT OR REPLACE INTO olm_sessions (
                        session_id, sender_key, pickle, account_id
                    ) VALUES (?, ?, ?, ?)
                """, (
                    session.id,
                    session.sender_key,
                    session.pickle,
                    self.account_id
                ))

            self.conn.commit()

    def save_outbound_group_sessions(self, sessions):
        with self.conn.cursor() as cur:
            for session in sessions:
                cur.execute("""
                    INSERT OR REPLACE INTO outbound_group_sessions (
                        room_id, session_id, pickle, account_id
                    ) VALUES (?, ?, ?, ?)
                """, (
                    session.room_id,
                    session.id,
                    session.pickle,
                    self.account_id
                ))

            self.conn.commit()

    def save_account(self, account: OlmAccount):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT OR REPLACE INTO accounts (
                    id, user_id, device_id, shared_account, pickle
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                self.account_id,
                self.user_id,
                self.device_id,
                account.shared,
                account.pickle(self.pickle_key),
            ))

            self.conn.commit()

    def load_sessions(self):
        session_store = SessionStore()

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    os.sender_key, os.session, os.creation_time
                FROM
                    olm_sessions os
                INNER JOIN
                    accounts a ON os.account_id = a.id
                WHERE
                    a.id = ?
            """, (self.account_id,))

            for row in cur.fetchall():
                sender_key, session_pickle, creation_time = row
                session = Session.from_pickle(
                    session_pickle, creation_time, self.pickle_key)
                session_store.add(sender_key, session)

        return session_store

    def load_inbound_group_sessions(self):
        # type: () -> GroupSessionStore
        """Load all Olm sessions from the database.

        Returns:
            ``GroupSessionStore`` object, containing all the loaded sessions.

        """
        store = GroupSessionStore()

        account = self.account_id

        if not account:
            return store

        with self.conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM inbound_group_sessions WHERE account_id = ?", (
                    account,)
            )

            for row in cursor.fetchall():
                cursor.execute(
                    "SELECT sender_key FROM forwarded_chains WHERE session_id = ?",
                    (row[1],),
                )
                chains = cursor.fetchall()

                session = InboundGroupSession.from_pickle(
                    row[2].encode(),
                    row[3],
                    row[4],
                    row[5],
                    self.pickle_key,
                    [
                        chain[0]
                        for chain in chains
                    ],
                )
                store.add(session)

        return store

    def load_outgoing_key_requests(self):
        # type: () -> dict
        """Load all outgoing key requests from the database.

        Returns:
            ``OutgoingKeyRequestStore`` object, containing all the loaded key requests.
        """
        account = self.account_id

        if not account:
            return store

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM outgoing_key_requests WHERE account_id = ?",
                (account,)
            )
            rows = cur.fetchall()

        return {
            row[1]: OutgoingKeyRequest.from_response(AttrDict({
                "id": row[0],
                "account_id": row[1],
                "request_id": row[2],
                "session_id": row[3],
                "room_id": row[4],
                "algorithm": row[5],
            })) for row in rows
        }

    def load_encrypted_rooms(self):
        """Load the set of encrypted rooms for this account.

        Returns:
            ``Set`` containing room ids of encrypted rooms.
        """
        account = self.account_id

        if not account:
            return set()

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT room_id FROM encrypted_rooms WHERE account_id = ?",
                (account,)
            )
            rows = cur.fetchall()

        return {row[0] for row in rows}

    def save_sync_token(self, token):
        """Save the given token"""
        account = self.account_id
        assert account

        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO sync_tokens (account_id, token) VALUES (?, ?)",
                (account, token)
            )
            self.conn.commit()

    def save_encrypted_rooms(self, rooms):
        """Save the set of room ids for this account."""
        account = self.account_id
        assert account

        data = [(room_id, account) for room_id in rooms]

        with self.conn.cursor() as cur:
            for idx in range(0, len(data), 400):
                rows = data[idx: idx + 400]
                cur.executemany(
                    "INSERT OR IGNORE INTO encrypted_rooms (room_id, account_id) VALUES (?, ?)",
                    rows
                )
            self.conn.commit()

    def save_session(self, sender_key, session):
        """Save the provided Olm session to the database.

        Args:
            sender_key (str): The curve key that owns the Olm session.
            session (Session): The Olm session that will be pickled and
                saved in the database.
        """
        account = self.account_id
        assert account

        pickled_session = session.pickle(self.pickle_key)

        with self.conn.cursor() as cur:

            cur.execute(
                "INSERT OR REPLACE INTO olm_sessions (account_id, sender_key, session, session_id, creation_time, last_usage_date) VALUES (?, ?, ?, ?, ?, ?)",
                (account, sender_key, pickled_session, session.id,
                 session.creation_time, session.use_time)
            )
            self.conn.commit()

    def save_inbound_group_session(self, session):
        """Save the provided Megolm inbound group session to the database.

        Args:
            session (InboundGroupSession): The session to save.
        """
        account = self.account_id
        assert account

        with self.conn.cursor() as cur:

            # Insert a new session or update the existing one
            query = """
            INSERT INTO inbound_group_sessions (account_id, sender_key, fp_key, room_id, session)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (account_id, sender_key, fp_key, room_id)
            DO UPDATE SET session = excluded.session
            """
            cur.execute(query, (account, session.sender_key,
                                session.ed25519, session.room_id, session.pickle(self.pickle_key)))

            # Delete existing forwarded chains for the session
            delete_query = """
            DELETE FROM forwarded_chains WHERE session_id = (SELECT id FROM inbound_group_sessions WHERE account_id = ? AND sender_key = ? AND fp_key = ? AND room_id = ?)
            """
            cur.execute(
                delete_query, (account, session.sender_key, session.ed25519, session.room_id))

            # Insert new forwarded chains for the session
            insert_query = """
            INSERT INTO forwarded_chains (session_id, sender_key)
            VALUES ((SELECT id FROM inbound_group_sessions WHERE account_id = ? AND sender_key = ? AND fp_key = ? AND room_id = ?), ?)
            """

            for chain in session.forwarding_chain:
                cur.execute(
                    insert_query, (account, session.sender_key, session.ed25519, session.room_id, chain))

    def add_outgoing_key_request(self, key_request):
        """Add a new outgoing key request to the database.

        Args:
            key_request (OutgoingKeyRequest): The key request to add.
        """

        account_id = self.account_id
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(id) FROM outgoing_key_requests
                """
            )
            row = cursor.fetchone()
            request_id = row[0] + 1 if row[0] else 1

            cursor.execute(
                """
                INSERT INTO outgoing_key_requests (id, account_id, request_id, session_id, room_id, algorithm)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (account_id, request_id) DO NOTHING
                """,
                (
                    request_id,
                    account_id,
                    key_request.request_id,
                    key_request.session_id,
                    key_request.room_id,
                    key_request.algorithm,
                )
            )

    def load_account(self):
        # type: () -> Optional[OlmAccount]
        """Load the Olm account from the database.

        Returns:
            ``OlmAccount`` object, or ``None`` if it wasn't found for the
                current device_id.

        """
        cursor = self.conn.cursor()
        query = """
            SELECT pickle, shared_account
            FROM accounts
            WHERE device_id = ?;
        """
        cursor.execute(query, (self.device_id,))

        result = cursor.fetchone()

        if not result:
            return None

        account_pickle, shared = result
        return OlmAccount.from_pickle(account_pickle.encode(), self.pickle_key, shared)
