"""The individual pipeline steps the runner exposes.

Each step is a thin wrapper over existing code: ``parse``/``audit`` reuse the
``ingest`` modules; ``train``/``merge``/``chat`` shell out to ``llamafactory-cli``.
Every step returns a process-style exit code (0 = success).
"""

import os
import subprocess
from typing import List, Optional

from ingest import banner, core, redactor, sharegpt
from ingest.adapters import available_sources, get_adapter
from ingest.cli import _load_dotenv
from ingest.validator import validate_samples

# ── Canonical artifact paths (one source of truth) ───────────────────────────
DATA_DIR = "data"
DEFAULT_INPUT = os.path.join(DATA_DIR, "result.json")
RAW_PATH = os.path.join(DATA_DIR, "chat_dataset.jsonl")        # parse output
DATASET_PATH = os.path.join(DATA_DIR, "chat_sharegpt.json")    # audit output (trains)
REPORT_PATH = os.path.join(DATA_DIR, "redaction_report.json")


def _resolve_config(stem: str) -> str:
    """Prefer a local override (``*.local.yaml``) over the tracked default."""
    local = os.path.join("configs", f"{stem}.local.yaml")
    return local if os.path.exists(local) else os.path.join("configs", f"{stem}.yaml")


def train_config() -> str:
    return _resolve_config("train_lora")


def export_config() -> str:
    return _resolve_config("export_lora")


def _read_yaml(path: str) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def adapter_dir() -> Optional[str]:
    """Where training writes the LoRA adapter (``output_dir`` in the config)."""
    try:
        return _read_yaml(train_config()).get("output_dir")
    except OSError:
        return None


# ── Status (for the menu's checkmarks / out-of-order guards) ──────────────────
def parse_done() -> bool:
    return os.path.exists(RAW_PATH)


def audit_done() -> bool:
    return os.path.exists(DATASET_PATH)


def train_done() -> bool:
    out = adapter_dir()
    return bool(out) and os.path.exists(os.path.join(out, "adapter_model.safetensors"))


# ── Steps ─────────────────────────────────────────────────────────────────────
def parse(
    source: str = "telegram",
    input_path: str = DEFAULT_INPUT,
    self_name: Optional[str] = None,
    conversation_gap: int = 3600,
    message_chain: int = 30,
    multi_speaker: bool = False,
    locales: Optional[List[str]] = None,
    scan: bool = True,
) -> int:
    """Stage 1: export → conversations → (scan). Writes raw samples + report.

    No redaction is applied here — that's :func:`audit`. The raw ``.jsonl`` holds
    unredacted text and is gitignored; treat it as sensitive.
    """
    if source not in available_sources():
        print(f"error: source '{source}' not supported. Choose: {', '.join(available_sources())}")
        return 2
    if not os.path.exists(input_path):
        print(f"error: input not found: {input_path}\n"
              f"       Place your export there or pass --input.")
        return 1

    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"Loading {input_path} via '{source}' adapter...")
    messages = get_adapter(source).parse(input_path, self_name=self_name)

    print("Building conversation samples...")
    samples = core.build_samples(
        messages,
        conversation_gap=conversation_gap,
        message_chain=message_chain,
        multi_speaker=multi_speaker,
    )
    print(f"Extracted {len(samples)} conversation samples.")

    if scan:
        report = redactor.scan_samples(samples, locales=locales)
        redactor.write_report(report, REPORT_PATH)
        redactor.print_summary(report, REPORT_PATH, mode="off")

    written = sharegpt.write_jsonl(samples, RAW_PATH)
    print(f"Wrote {written} raw conversation samples to {RAW_PATH}.")
    print(f"Next: review {REPORT_PATH}, then run `audit`.")
    return 0


def audit(
    redact: str = "replace",
    locales: Optional[List[str]] = None,
    validate: bool = True,
) -> int:
    """Stage 2: review scan → redact → (optional LLM quality audit) → dataset.

    Consumes the raw ``.jsonl`` from :func:`parse` and writes the training-ready
    ShareGPT dataset.
    """
    if not parse_done():
        print(f"error: {RAW_PATH} not found — run `parse` first.")
        return 1

    samples = sharegpt.load_jsonl_samples(RAW_PATH)
    print(f"Loaded {len(samples)} conversation samples from {RAW_PATH}.")

    # Re-derive the scan summary so audit is self-contained (regex is cheap).
    report = redactor.scan_samples(samples, locales=locales)
    redactor.write_report(report, REPORT_PATH)
    redactor.print_summary(report, REPORT_PATH, mode=redact)

    if redact != "off":
        before = len(samples)
        samples = redactor.apply(samples, redact, locales=locales)
        print(f"[redactor] Applied --redact {redact}: {before} -> {len(samples)} samples.")

    if validate:
        samples = validate_samples(samples)  # self-disables if no LLM configured

    written = sharegpt.write_sharegpt(samples, DATASET_PATH)
    print(f"Wrote {written} ShareGPT samples to {DATASET_PATH}.")
    print("Next: run `train`.")
    return 0


def _llamafactory(args: List[str], gpus: Optional[str] = None) -> int:
    env = dict(os.environ)
    if gpus:
        env["CUDA_VISIBLE_DEVICES"] = gpus
    print(f"$ llamafactory-cli {' '.join(args)}"
          + (f"   (CUDA_VISIBLE_DEVICES={gpus})" if gpus else ""))
    try:
        return subprocess.run(["llamafactory-cli", *args], env=env).returncode
    except FileNotFoundError:
        print("error: llamafactory-cli not found. Activate the venv (and `pip install -r requirements.txt`).")
        return 127


def train(config: Optional[str] = None, gpus: Optional[str] = None) -> int:
    """Stage 3: LoRA fine-tune via LLaMA-Factory."""
    if not audit_done():
        print(f"warning: {DATASET_PATH} not found — run `parse` + `audit` (or `auto`) first.")
        return 1
    return _llamafactory(["train", config or train_config()], gpus=gpus)


def merge(config: Optional[str] = None, gpus: Optional[str] = None) -> int:
    """Stage 4 (optional): merge the LoRA adapter into the base model."""
    return _llamafactory(["export", config or export_config()], gpus=gpus)


def chat(gpus: Optional[str] = None) -> int:
    """Stage 5: chat with the fine-tuned model (base + adapter, nothing merged)."""
    cfg = _read_yaml(train_config())
    out = cfg.get("output_dir")
    if not out or not os.path.exists(os.path.join(out, "adapter_model.safetensors")):
        print(f"warning: no trained adapter at {out!r} — run `train` first.")
        return 1
    return _llamafactory([
        "chat",
        "--model_name_or_path", cfg.get("model_name_or_path", ""),
        "--adapter_name_or_path", out,
        "--template", cfg.get("template", "default"),
        "--finetuning_type", "lora",
        "--infer_dtype", "bfloat16",
    ], gpus=gpus)


def auto(
    do_train: bool = False,
    redact: str = "replace",
    gpus: Optional[str] = None,
    **parse_kwargs,
) -> int:
    """Run the pipeline end-to-end, unattended (like the old one-shot ingest).

    parse → audit (redact, no review pause) → dataset. With ``do_train`` it also
    chains training. Redaction defaults to ``replace`` so it never trains on raw
    PII without an explicit opt-out (``redact='off'``).
    """
    banner.print_banner()
    print("=== auto: running the full pipeline (no review pause) ===")
    if redact == "off":
        print("WARNING: --redact off — sensitive data will NOT be removed.")
    rc = parse(**parse_kwargs)
    if rc:
        return rc
    rc = audit(redact=redact, locales=parse_kwargs.get("locales"))
    if rc:
        return rc
    if do_train:
        rc = train(gpus=gpus)
    return rc


# Ordered for the menu.
STEPS = [
    ("parse", "Parse export → conversations + sensitive-data scan", parse_done),
    ("audit", "Review scan → redact → training-ready dataset", audit_done),
    ("train", "LoRA fine-tune on the dataset", train_done),
    ("merge", "Merge the LoRA adapter into the base model (optional)", lambda: False),
    ("chat", "Chat with the fine-tuned model", lambda: False),
]


def load_env() -> None:
    _load_dotenv()
