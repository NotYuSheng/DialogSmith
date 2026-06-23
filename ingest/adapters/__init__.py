"""Source adapters.

Importing this package registers every built-in adapter. To add a new source,
create a module here that builds a :class:`~ingest.adapters.base.SourceAdapter`
and calls ``register(...)`` on it, then import it below.
"""

from ingest.adapters.base import (  # noqa: F401
    SourceAdapter,
    available_sources,
    get_adapter,
    register,
)

# Importing each adapter module registers it. (Only Telegram for now —
# WhatsApp/Signal/etc. would each be one more import here.)
from ingest.adapters import telegram  # noqa: F401,E402
