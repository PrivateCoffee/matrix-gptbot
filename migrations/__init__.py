from collections import OrderedDict
from typing import Optional

from duckdb import DuckDBPyConnection

from .migration_1 import migration as migration_1
from .migration_2 import migration as migration_2
from .migration_3 import migration as migration_3
from .migration_4 import migration as migration_4

MIGRATIONS = OrderedDict()

MIGRATIONS[1] = migration_1
MIGRATIONS[2] = migration_2
MIGRATIONS[3] = migration_3
MIGRATIONS[4] = migration_4

def get_version(db: DuckDBPyConnection) -> int:
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

def migrate(db: DuckDBPyConnection, from_version: Optional[int] = None, to_version: Optional[int] = None) -> None:
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
        if version in MIGRATIONS:
            MIGRATIONS[version + 1](db)

    return from_version, to_version