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
            t.get("text", "") if isinstance(t, dict) else str(t)
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
        if not self_name:
            raise ValueError(
                "Could not detect your name from the export's personal_information. "
                "Provide it manually with --self-name (otherwise every message would be "
                "treated as 'not you' and all conversations dropped)."
            )
        print(f"[telegram] Detected user name: {self_name!r}")

        messages: List[NormalizedMessage] = []
        for idx, chat in enumerate(data.get("chats", {}).get("list", [])):
            chat_id = str(chat.get("id", f"chat_{idx}"))
            for msg in chat.get("messages", []):
                if not _is_valid(msg):
                    continue
                # "from" can be missing/None (e.g. anonymous channel posts); fall
                # back to a label so sender_id stays a str (and multi-speaker
                # mode doesn't emit a "None: " prefix).
                sender = msg.get("from") or "Unknown"
                reply_to = msg.get("reply_to_message_id")
                msg_id = msg.get("id")
                messages.append(
                    NormalizedMessage(
                        chat_id=chat_id,
                        timestamp=int(msg["date_unixtime"]),
                        sender_id=sender,
                        sender_is_self=(sender == self_name),
                        text=_get_text(msg),
                        message_id=str(msg_id) if msg_id is not None else None,
                        reply_to_id=str(reply_to) if reply_to is not None else None,
                    )
                )
        return messages


register(TelegramAdapter())
