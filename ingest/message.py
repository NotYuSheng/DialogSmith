"""The normalized, source-agnostic message shape shared by the pipeline."""

from dataclasses import dataclass


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
    """

    chat_id: str
    timestamp: int
    sender_id: str
    sender_is_self: bool
    text: str
