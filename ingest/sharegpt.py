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


def to_sharegpt(samples: List[Sample]) -> list:
    """Convert role/text samples to ShareGPT ``{"conversations": [...]}`` records.

    Drops empty turns and keeps only samples that contain both a human and a gpt
    turn (LLaMA-Factory needs both sides to train on).
    """
    output = []
    for turns in samples:
        conversations = []
        for turn in turns:
            speaker = ROLE_MAP.get(turn.get("role", ""), turn.get("role", ""))
            value = turn.get("text", "").strip()
            if speaker and value:
                conversations.append({"from": speaker, "value": value})

        roles_present = {c["from"] for c in conversations}
        if "human" not in roles_present or "gpt" not in roles_present:
            continue

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
