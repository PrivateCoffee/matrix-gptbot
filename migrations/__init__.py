from collections import OrderedDict

from .migration_1 import migration as migration_1
from .migration_2 import migration as migration_2
from .migration_3 import migration as migration_3

MIGRATIONS = OrderedDict()

MIGRATIONS[1] = migration_1
MIGRATIONS[2] = migration_2
MIGRATIONS[3] = migration_3