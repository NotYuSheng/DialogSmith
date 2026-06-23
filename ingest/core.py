"""Platform-agnostic pipeline core.

Operates purely on :class:`~ingest.message.NormalizedMessage` streams, so it is
identical for every source. Two tunables:

* ``conversation_gap`` — seconds of silence that start a new conversation.
* ``message_chain`` — max seconds between same-sender messages for them to be
  merged into a single turn.

A *sample* is a list of ``{"role": "user"|"assistant", "text": ...}`` turns.
"""

from typing import Dict, Iterable, List

from ingest.message import NormalizedMessage

DEFAULT_CONVERSATION_GAP = 3600  # 1 hour of silence starts a new conversation
DEFAULT_MESSAGE_CHAIN = 30       # consecutive same-sender messages within 30s chain into one turn

Turn = Dict[str, str]
Sample = List[Turn]


def _group_by_chat(messages: Iterable[NormalizedMessage]) -> List[List[NormalizedMessage]]:
    """Group messages by ``chat_id``, preserving first-seen order.

    Conversations never span chats, so each chat is processed independently.
    """
    groups: "Dict[str, List[NormalizedMessage]]" = {}
    for msg in messages:
        groups.setdefault(msg.chat_id, []).append(msg)
    return list(groups.values())


def _split_into_conversations(
    messages: List[NormalizedMessage], gap_threshold: int
) -> List[List[NormalizedMessage]]:
    """Split one chat's messages into conversations on silence gaps."""
    conversations: List[List[NormalizedMessage]] = []
    current: List[NormalizedMessage] = []
    last_ts = None

    for msg in messages:
        if last_ts is not None and (msg.timestamp - last_ts) > gap_threshold:
            if current:
                conversations.append(current)
            current = []
        current.append(msg)
        last_ts = msg.timestamp

    if current:
        conversations.append(current)

    return conversations


def _collect_turn(
    conversation: List[NormalizedMessage], start_idx: int, chain_threshold: int
):
    """Collect consecutive messages from one sender starting at ``start_idx``.

    Chains them while each is within ``chain_threshold`` seconds of the previous
    one in the chain. Returns ``(texts, next_idx)``.
    """
    sender = conversation[start_idx].sender_id
    texts: List[str] = []
    last_ts = None
    j = start_idx

    while j < len(conversation):
        msg = conversation[j]
        if msg.sender_id != sender:
            break
        if last_ts is not None and (msg.timestamp - last_ts) > chain_threshold:
            break
        texts.append(msg.text)
        last_ts = msg.timestamp
        j += 1

    return texts, j


def build_samples(
    messages: Iterable[NormalizedMessage],
    conversation_gap: int = DEFAULT_CONVERSATION_GAP,
    message_chain: int = DEFAULT_MESSAGE_CHAIN,
) -> List[Sample]:
    """Turn normalized messages into multi-turn conversation samples.

    Splits each chat into conversations, merges consecutive same-sender messages
    into turns, and keeps only conversations containing at least one user turn
    and one assistant turn.
    """
    samples: List[Sample] = []

    for chat_messages in _group_by_chat(messages):
        for conversation in _split_into_conversations(chat_messages, conversation_gap):
            turns: Sample = []
            i = 0
            while i < len(conversation):
                texts, next_i = _collect_turn(conversation, i, message_chain)
                if texts:
                    role = "assistant" if conversation[i].sender_is_self else "user"
                    turn_text = "\n".join(texts)
                    # Merge with previous turn if same role (e.g. gap split a block).
                    if turns and turns[-1]["role"] == role:
                        turns[-1]["text"] += "\n" + turn_text
                    else:
                        turns.append({"role": role, "text": turn_text})
                i = next_i

            roles = {t["role"] for t in turns}
            if "user" in roles and "assistant" in roles:
                samples.append(turns)

    return samples
