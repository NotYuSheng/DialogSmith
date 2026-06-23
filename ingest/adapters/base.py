"""Source-adapter protocol and registry.

An adapter is anything with a ``name`` and a ``parse(path, *, self_name=None)``
method that yields :class:`~ingest.message.NormalizedMessage` objects. Adapters
register themselves at import time via :func:`register`; the CLI looks them up
with :func:`get_adapter`. Adding a new chat source therefore requires only a new
module under ``ingest/adapters/`` — no changes to the core pipeline.
"""

from typing import Iterable, Optional, Protocol, runtime_checkable

from ingest.message import NormalizedMessage


@runtime_checkable
class SourceAdapter(Protocol):
    name: str

    def parse(
        self, path: str, *, self_name: Optional[str] = None
    ) -> Iterable[NormalizedMessage]:
        """Parse a raw export at ``path`` into normalized messages."""
        ...


_REGISTRY: "dict[str, SourceAdapter]" = {}


def register(adapter: SourceAdapter) -> SourceAdapter:
    """Register an adapter instance under its ``name``."""
    _REGISTRY[adapter.name] = adapter
    return adapter


def available_sources() -> "list[str]":
    return sorted(_REGISTRY)


def get_adapter(name: str) -> SourceAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        supported = ", ".join(available_sources()) or "(none)"
        raise ValueError(
            f"Source {name!r} is not supported yet. Supported sources: {supported}."
        )
