#!/usr/bin/env python3
"""DEPRECATED shim — kept for backwards compatibility, removed in a future release.

Use the cross-platform CLI instead:

    python -m ingest --source telegram --format jsonl

This shim reproduces the old behaviour (Telegram result.json ->
data/chat_dataset.jsonl) by delegating to the new ``ingest`` package.
"""

import os
import sys

# Allow running as `python scripts/telegram_extract.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.stderr.write(
        "[deprecated] scripts/telegram_extract.py -> use: "
        "python -m ingest --source telegram --format jsonl\n"
    )
    raise SystemExit(
        main(["--source", "telegram", "--format", "jsonl",
              "--output", "./data/chat_dataset.jsonl"])
    )
