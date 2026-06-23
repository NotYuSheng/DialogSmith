"""Telegram Desktop JSON export adapter.

Parses a ``result.json`` produced by Telegram Desktop
(``Settings > Advanced > Export Telegram Data``, JSON format) into normalized
messages. All Telegram-specific schema knowledge lives here; the downstream
pipeline never sees a raw Telegram message.
"""

import json
from typing import List, Optional

from ingest.adapters.base import register
from ingest.message import NormalizedMessage


def _detect_self_name(data: dict) -> str:
    """The export owner's display name, from ``personal_information``."""
    info = data.get("personal_information", {})
    first = info.get("first_name", "")
    last = info.get("last_name", "")
    return f"{first} {last}".strip()


def _get_text(msg: dict) -> str:
    """Extract plain text, handling both string and entity-list formats."""
    text = msg.get("text", "")
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, list):
        return "".join(
            t["text"] if isinstance(t, dict) else t
            for t in msg.get("text_entities", text)
        ).strip()
    return ""


def _is_valid(msg: dict) -> bool:
    """A real text message (not a service/media-only event)."""
    return msg.get("type") == "message" and bool(_get_text(msg))


class TelegramAdapter:
    name = "telegram"

    def parse(
        self, path: str, *, self_name: Optional[str] = None
    ) -> List[NormalizedMessage]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if self_name is None:
            self_name = _detect_self_name(data)
        print(f"[telegram] Detected user name: {self_name!r}")

        messages: List[NormalizedMessage] = []
        for idx, chat in enumerate(data.get("chats", {}).get("list", [])):
            chat_id = str(chat.get("id", f"chat_{idx}"))
            for msg in chat.get("messages", []):
                if not _is_valid(msg):
                    continue
                sender = msg.get("from")
                messages.append(
                    NormalizedMessage(
                        chat_id=chat_id,
                        timestamp=int(msg["date_unixtime"]),
                        sender_id=sender,
                        sender_is_self=(sender == self_name),
                        text=_get_text(msg),
                    )
                )
        return messages


register(TelegramAdapter())
