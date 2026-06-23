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
    """Group messages by ``chat_id``, each sorted chronologically.

    Conversations never span chats, so each chat is processed independently.
    Messages are sorted by timestamp (stable, so same-timestamp order is
    preserved) because not every source guarantees chronological order.
    """
    groups: "Dict[str, List[NormalizedMessage]]" = {}
    for msg in messages:
        groups.setdefault(msg.chat_id, []).append(msg)
    return [sorted(g, key=lambda m: m.timestamp) for g in groups.values()]


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


def _merge_by_reply(
    conversations: List[List[NormalizedMessage]],
) -> List[List[NormalizedMessage]]:
    """Stitch back conversations that a silence gap split but a reply connects.

    A time gap is a guess at where one conversation ends. An explicit reply link
    is ground truth: if a message replies to one in an earlier (same-chat)
    conversation, they belong together. We union such conversations and re-sort
    each merged group chronologically.

    When no message carries reply metadata (``message_id``/``reply_to_id`` all
    ``None``), there is nothing to union and the input is returned unchanged — so
    sources without reply data keep the pure time-based behaviour.
    """
    n = len(conversations)
    if n <= 1:
        return conversations

    id_to_conv = {
        m.message_id: ci
        for ci, conv in enumerate(conversations)
        for m in conv
        if m.message_id is not None
    }
    if not id_to_conv:
        return conversations

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for ci, conv in enumerate(conversations):
        for m in conv:
            target = id_to_conv.get(m.reply_to_id) if m.reply_to_id else None
            if target is not None and target != ci:
                union(ci, target)

    groups: "Dict[int, List[NormalizedMessage]]" = {}
    for ci in range(n):
        groups.setdefault(find(ci), []).extend(conversations[ci])

    # Order merged groups by their earliest message so output stays chronological.
    ordered_roots = sorted(groups, key=lambda r: min(m.timestamp for m in groups[r]))
    return [sorted(groups[r], key=lambda m: m.timestamp) for r in ordered_roots]


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


def _assemble_turns(raw_turns, multi_speaker: bool) -> Sample:
    """Turn ``(sender_id, is_self, text)`` runs into role/text turns.

    Roles: the dataset owner is ``assistant`` (this is what the doppelganger
    learns to produce, so it is *never* labelled), everyone else is ``user``.

    Default mode merges adjacent same-role runs, so in a group chat several
    people on the "other side" collapse into one ``user`` turn. ``multi_speaker``
    instead keeps each speaker distinct and prefixes ``user`` turns with the
    sender (``"Bob: ..."``), only merging consecutive runs from the *same*
    sender — preserving who-said-what as conditioning context.
    """
    turns: Sample = []
    last_sender = None

    for sender_id, is_self, text in raw_turns:
        role = "assistant" if is_self else "user"

        same_role = bool(turns) and turns[-1]["role"] == role
        # In multi-speaker mode a user turn only merges with the previous turn
        # when it is the same speaker; otherwise distinct speakers stay distinct.
        mergeable = same_role and not (
            multi_speaker and role == "user" and last_sender != sender_id
        )
        if mergeable:
            # Continuation of the same turn — don't repeat the speaker prefix.
            turns[-1]["text"] += "\n" + text
        else:
            value = f"{sender_id}: {text}" if (multi_speaker and role == "user") else text
            turns.append({"role": role, "text": value})
        last_sender = sender_id

    return turns


def build_samples(
    messages: Iterable[NormalizedMessage],
    conversation_gap: int = DEFAULT_CONVERSATION_GAP,
    message_chain: int = DEFAULT_MESSAGE_CHAIN,
    multi_speaker: bool = False,
) -> List[Sample]:
    """Turn normalized messages into multi-turn conversation samples.

    Splits each chat into conversations (stitching reply-linked ones back
    together), merges consecutive same-sender messages into turns, and keeps
    only conversations containing at least one user turn and one assistant turn.

    ``multi_speaker`` preserves and labels individual senders in group chats
    (see :func:`_assemble_turns`); the default collapses the other side.
    """
    samples: List[Sample] = []

    for chat_messages in _group_by_chat(messages):
        time_convs = _split_into_conversations(chat_messages, conversation_gap)
        for conversation in _merge_by_reply(time_convs):
            raw_turns = []
            i = 0
            while i < len(conversation):
                texts, next_i = _collect_turn(conversation, i, message_chain)
                if texts:
                    m = conversation[i]
                    raw_turns.append((m.sender_id, m.sender_is_self, "\n".join(texts)))
                i = next_i

            turns = _assemble_turns(raw_turns, multi_speaker)
            roles = {t["role"] for t in turns}
            if "user" in roles and "assistant" in roles:
                samples.append(turns)

    return samples
