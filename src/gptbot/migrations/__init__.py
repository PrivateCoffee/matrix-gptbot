from collections import OrderedDict
from typing import Optional
from importlib import import_module

from peewee import SqliteDatabase


MAX_MIGRATION = 8

MIGRATIONS = OrderedDict()

for i in range(1, MAX_MIGRATION + 1):
    MIGRATIONS[i] = import_module(f".migration_{i}", __package__).migration

def get_version(db: SqliteDatabase) -> int:
    """Get the current database version.

    Args:
        db (DuckDBPyConnection): Database connection.

    Returns:
        int: Current database version.
    """

    try:
        return int(db.execute("SELECT MAX(id) FROM migrations").fetchone()[0])
    except:
        return 0

def migrate(db: SqliteDatabase, from_version: Optional[int] = None, to_version: Optional[int] = None) -> None:
    """Migrate the database to a specific version.

    Args:
        db (DuckDBPyConnection): Database connection.
        from_version (Optional[int]): Version to migrate from. If None, the current version is used.
        to_version (Optional[int]): Version to migrate to. If None, the latest version is used.
    """

    if from_version is None:
        from_version = get_version(db)

    if to_version is None:
        to_version = max(MIGRATIONS.keys())

    if from_version > to_version:
        raise ValueError("Cannot migrate from a higher version to a lower version.")

    for version in range(from_version, to_version):
        if version + 1 in MIGRATIONS:
            MIGRATIONS[version + 1](db)

    return from_version, to_version
