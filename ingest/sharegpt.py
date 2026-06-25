"""ShareGPT formatting and dataset I/O.

Converts the core's role/text samples into the ShareGPT shape LLaMA-Factory
consumes, and reads/writes the on-disk dataset formats.
"""

import json
from typing import List

from ingest.core import Sample

# Core roles -> ShareGPT speaker tags (matches configs/dataset_info.json).
ROLE_MAP = {
    "user": "human",
    "assistant": "gpt",
}


def _coerce_alternating(conversations: list) -> list:
    """Coerce a ``{"from", "value"}`` turn list into the shape LLaMA-Factory's
    ShareGPT converter accepts: starts with ``human``, strictly alternates
    ``human``/``gpt``, and ends with ``gpt`` (even number of turns).

    LLaMA-Factory enforces ``messages[i]`` is human for even ``i`` and gpt for
    odd ``i``, and rejects odd-length conversations outright. Raw chats break
    both rules constantly (the other person messages first; same-speaker runs
    survive reply-stitching / multi-speaker labelling), so without this they are
    silently dropped at train time. We salvage them instead of discarding:

    - merge consecutive same-speaker turns (labels stay embedded in the text),
    - drop leading ``gpt`` turns so it starts on ``human``,
    - drop the trailing ``human`` turn so it ends on ``gpt``.

    Returns ``[]`` if no ``human -> gpt`` pair survives.
    """
    merged: list = []
    for turn in conversations:
        if merged and merged[-1]["from"] == turn["from"]:
            merged[-1]["value"] = f"{merged[-1]['value']}\n{turn['value']}"
        else:
            merged.append(dict(turn))

    while merged and merged[0]["from"] != "human":
        merged.pop(0)
    while merged and merged[-1]["from"] != "gpt":
        merged.pop()

    return merged if len(merged) >= 2 else []


def to_sharegpt(samples: List[Sample]) -> list:
    """Convert role/text samples to ShareGPT ``{"conversations": [...]}`` records.

    Drops empty turns, then coerces each sample into the strictly-alternating
    ``human -> gpt -> ...`` shape LLaMA-Factory requires (see
    :func:`_coerce_alternating`). Samples with no usable ``human -> gpt`` pair
    are dropped.
    """
    output = []
    for turns in samples:
        conversations = []
        for turn in turns:
            speaker = ROLE_MAP.get(turn.get("role", ""), turn.get("role", ""))
            value = turn.get("text", "").strip()
            if speaker and value:
                conversations.append({"from": speaker, "value": value})

        conversations = _coerce_alternating(conversations)
        if conversations:
            output.append({"conversations": conversations})
    return output


def write_jsonl(samples: List[Sample], path: str) -> int:
    """Write raw role/text samples, one ``{"conversations": [...]}`` per line."""
    with open(path, "w", encoding="utf-8") as f:
        for turns in samples:
            json.dump({"conversations": turns}, f, ensure_ascii=False)
            f.write("\n")
    return len(samples)


def write_sharegpt(samples: List[Sample], path: str) -> int:
    """Write samples as a ShareGPT JSON array. Returns count actually written."""
    data = to_sharegpt(samples)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return len(data)


def load_jsonl_samples(path: str) -> List[Sample]:
    """Read role/text samples back from a ``chat_dataset.jsonl`` file."""
    samples: List[Sample] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            turns = record.get("conversations", [])
            if turns:
                samples.append(turns)
    return samples
