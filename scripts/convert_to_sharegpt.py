#!/usr/bin/env python3
"""DEPRECATED shim — kept for backwards compatibility, removed in a future release.

The new pipeline writes ShareGPT directly:

    python -m ingest --source telegram --format sharegpt

This shim still converts an existing data/chat_dataset.jsonl into
data/chat_sharegpt.json, delegating to the new ``ingest`` package.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest import sharegpt  # noqa: E402

INPUT_PATH = "./data/chat_dataset.jsonl"
OUTPUT_PATH = "./data/chat_sharegpt.json"

if __name__ == "__main__":
    sys.stderr.write(
        "[deprecated] scripts/convert_to_sharegpt.py -> use: "
        "python -m ingest --source telegram --format sharegpt\n"
    )
    samples = sharegpt.load_jsonl_samples(INPUT_PATH)
    written = sharegpt.write_sharegpt(samples, OUTPUT_PATH)
    print(f"Converted {written} valid conversation samples to ShareGPT format.")
