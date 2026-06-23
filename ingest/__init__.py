"""Chat-history ingestion pipeline.

Turns a raw chat export from some source (currently Telegram) into a
fine-tuning dataset. The only source-specific code is the *adapter* that parses
a raw export into a stream of :class:`~ingest.message.NormalizedMessage`; every
step after that (sessionizing, turn-merging, validation, ShareGPT formatting) is
shared across sources. Adding a new platform means adding one adapter — see
``ingest/adapters/``.
"""

__all__ = ["NormalizedMessage"]

from ingest.message import NormalizedMessage
