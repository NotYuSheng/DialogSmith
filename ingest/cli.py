"""Command-line entrypoint: raw chat export -> fine-tuning dataset.

    python -m ingest --source telegram --input data/result.json

Pipeline: adapter (parse) -> core (build samples) -> validator (optional LLM
filter) -> writer (ShareGPT or raw JSONL).
"""

import argparse
import os
import sys

import os.path

from ingest import core, redactor, sharegpt
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


def _run_llm_redaction(samples, allow_cloud: bool):
    """Run the optional LLM redaction pass, guarding against accidental cloud use.

    Returns a (possibly empty) list of LLM findings. Prefers a local endpoint;
    if none is configured and cloud use wasn't explicitly allowed, it warns and
    skips rather than silently shipping chat data to a third party.
    """
    from ingest import llm

    if not llm.is_local() and not allow_cloud:
        print(
            "[redactor] --llm-redact set but no local endpoint configured. "
            "Refusing to send chat data to a hosted API by default. Set "
            f"{llm.BASE_URL_ENV} to a local OpenAI-compatible server (Ollama, "
            "vLLM, LM Studio, ...), or pass --allow-cloud-redaction to override. "
            "Skipping LLM pass."
        )
        return []

    try:
        client = llm.get_client()
    except (ImportError, EnvironmentError) as e:
        print(f"[redactor] LLM redaction unavailable: {e}. Skipping LLM pass.")
        return []

    model = llm.model()
    print(f"[redactor] LLM redaction scan via {model} ({llm.endpoint_label()})...")
    return redactor.llm_scan_samples(samples, client, model)


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
    parser.add_argument(
        "--multi-speaker",
        action="store_true",
        help="In group chats, keep individual senders and label each user turn "
        "with their name (e.g. 'Bob: ...'). Your own turns are never labelled. "
        "Default collapses the other side into one speaker.",
    )
    parser.add_argument(
        "--redact",
        choices=["off", "replace", "drop"],
        default="off",
        help="What to do with detected sensitive data. 'off' (default) only "
        "scans and writes a report. 'replace' swaps spans for [CATEGORY] "
        "placeholders; 'drop' removes conversations containing detections.",
    )
    parser.add_argument(
        "--redact-locales",
        default="SG",
        help="Comma-separated locales for sensitive-data detection (universal "
        "patterns always run). Default: SG.",
    )
    parser.add_argument(
        "--skip-redact-scan",
        action="store_true",
        help="Skip the sensitive-data scan/report entirely.",
    )
    parser.add_argument(
        "--llm-redact",
        action="store_true",
        help="Additionally use an LLM to flag context-dependent sensitive data "
        "(names, secrets regex misses). Prefers a local endpoint: set "
        "LLM_API_BASE_URL, or pass --allow-cloud-redaction to use a hosted API "
        "(which sends chat text to a third party).",
    )
    parser.add_argument(
        "--allow-cloud-redaction",
        action="store_true",
        help="Permit LLM redaction against a hosted API when no local "
        "LLM_API_BASE_URL is configured.",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="Master off-switch: skip ALL auditing — the regex sensitive-data "
        "scan and the LLM quality validation. Just build the dataset.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip only the LLM quality validation (the regex scan still runs "
        "unless --skip-redact-scan / --no-audit is also given).",
    )
    return parser


def main(argv=None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)

    from ingest import banner
    banner.print_banner()

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
        multi_speaker=args.multi_speaker,
    )
    print(f"Extracted {len(samples)} conversation samples.")

    # --no-audit is the master off-switch; the granular flags disable one half.
    skip_scan = args.no_audit or args.skip_redact_scan
    skip_validation = args.no_audit or args.skip_validation
    if args.no_audit:
        print("[audit] All auditing disabled (--no-audit) — building dataset as-is.")

    locales = [s.strip() for s in args.redact_locales.split(",") if s.strip()]
    llm_findings = []
    if not skip_scan:
        report = redactor.scan_samples(samples, locales=locales)
        if args.llm_redact:
            llm_findings = _run_llm_redaction(samples, args.allow_cloud_redaction)
            redactor.merge_llm_findings(report, llm_findings)
        report_path = os.path.join(os.path.dirname(output) or ".", "redaction_report.json")
        redactor.write_report(report, report_path)
        redactor.print_summary(report, report_path, mode=args.redact)

    # --redact is an explicit request, so honour it even when the scan/report was
    # skipped — otherwise the dataset would silently keep sensitive data.
    if args.redact != "off":
        if skip_scan:
            print(
                f"[redactor] Scan skipped, but --redact {args.redact} was requested — "
                "applying regex redaction (note: --llm-redact needs the scan)."
            )
        before = len(samples)
        samples = redactor.apply(
            samples, args.redact, locales=locales, llm_findings=llm_findings
        )
        print(
            f"[redactor] Applied --redact {args.redact}: "
            f"{before} -> {len(samples)} samples."
        )

    if not skip_validation:
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
