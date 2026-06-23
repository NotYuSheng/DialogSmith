"""The normalized, source-agnostic message shape shared by the pipeline."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedMessage:
    """A single chat message, decoupled from any platform's export format.

    Adapters are responsible for producing these; the core pipeline only ever
    sees normalized messages, so it never needs to know which platform a
    message came from.

    Attributes:
        chat_id: Stable identifier for the conversation/chat this message
            belongs to. Messages are grouped by this; conversations never span
            two chats.
        timestamp: Unix time (seconds) the message was sent. Used for
            sessionizing and turn-chaining.
        sender_id: Opaque identifier for the sender (display name, phone
            number, numeric id — whatever the source provides). Used only to
            tell consecutive senders apart.
        sender_is_self: Whether this message was sent by the dataset owner
            ("you"). Drives the user/assistant role assignment downstream.
        text: The plain-text message body (already extracted/cleaned by the
            adapter). Adapters should only emit messages with non-empty text.
        message_id: Source-stable id for this message, used to resolve reply
            links. ``None`` if the source has no message ids.
        reply_to_id: ``message_id`` of the message this one replies to, or
            ``None``. Lets the pipeline thread replies instead of relying on
            time order alone. Adapters that lack reply data leave both ``None``,
            and grouping falls back to its time-based behaviour.
    """

    chat_id: str
    timestamp: int
    sender_id: str
    sender_is_self: bool
    text: str
    message_id: Optional[str] = None
    reply_to_id: Optional[str] = None
