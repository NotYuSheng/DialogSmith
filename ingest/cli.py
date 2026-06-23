"""Command-line entrypoint: raw chat export -> fine-tuning dataset.

    python -m ingest --source telegram --input data/result.json

Pipeline: adapter (parse) -> core (build samples) -> validator (optional LLM
filter) -> writer (ShareGPT or raw JSONL).
"""

import argparse
import os
import sys

from ingest import core, sharegpt
from ingest.adapters import available_sources, get_adapter
from ingest.validator import validate_samples

DEFAULT_INPUT = "./data/result.json"
SHAREGPT_OUTPUT = "./data/chat_sharegpt.json"
JSONL_OUTPUT = "./data/chat_dataset.jsonl"


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no dependency).

    Sets ``KEY=VALUE`` pairs from ``path`` into the environment without
    overriding variables already set in the real environment.
    """
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ingest",
        description="Convert a chat export into a fine-tuning dataset.",
    )
    parser.add_argument(
        "--source",
        default="telegram",
        help=f"Chat source to parse. Supported: {', '.join(available_sources())}. "
        "(More sources are planned — each is a drop-in adapter.)",
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Path to the raw export (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path. Defaults to data/chat_sharegpt.json (sharegpt) "
        "or data/chat_dataset.jsonl (jsonl).",
    )
    parser.add_argument(
        "--format",
        choices=["sharegpt", "jsonl"],
        default="sharegpt",
        help="Output format (default: sharegpt — what training consumes).",
    )
    parser.add_argument(
        "--self-name",
        default=None,
        help="Override auto-detection of which sender is you.",
    )
    parser.add_argument(
        "--conversation-gap",
        type=int,
        default=core.DEFAULT_CONVERSATION_GAP,
        help=f"Seconds of silence that start a new conversation "
        f"(default: {core.DEFAULT_CONVERSATION_GAP}).",
    )
    parser.add_argument(
        "--message-chain",
        type=int,
        default=core.DEFAULT_MESSAGE_CHAIN,
        help=f"Max seconds between same-sender messages to merge into one turn "
        f"(default: {core.DEFAULT_MESSAGE_CHAIN}).",
    )
    return parser


def main(argv=None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)

    try:
        adapter = get_adapter(args.source)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    output = args.output or (
        SHAREGPT_OUTPUT if args.format == "sharegpt" else JSONL_OUTPUT
    )

    print(f"Loading {args.input} via '{args.source}' adapter...")
    messages = adapter.parse(args.input, self_name=args.self_name)

    print("Building conversation samples...")
    samples = core.build_samples(
        messages,
        conversation_gap=args.conversation_gap,
        message_chain=args.message_chain,
    )
    print(f"Extracted {len(samples)} conversation samples.")

    samples = validate_samples(samples)

    if args.format == "sharegpt":
        written = sharegpt.write_sharegpt(samples, output)
        print(f"Wrote {written} ShareGPT samples to {output}.")
    else:
        written = sharegpt.write_jsonl(samples, output)
        print(f"Wrote {written} samples to {output}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
