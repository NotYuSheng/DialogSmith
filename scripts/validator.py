"""
Optional LLM-based conversation quality validator.

Controlled via environment variables:
  DIALOGSMITH_LLM_VALIDATE=true/false   (default: true if ANTHROPIC_API_KEY is set)
  DIALOGSMITH_LLM_MODEL=...             (default: claude-haiku-4-5-20251001)
  ANTHROPIC_API_KEY=...

Each conversation sample is scored on two axes:
  - coherence: does this read as a natural, continuous conversation?
  - quality:   is this a meaningful exchange worth training on?

Samples that fail either check are excluded from the output.
A summary of filtered samples is printed so the user can audit decisions.
"""

import json
import os
import re

VALIDATE_ENV = "DIALOGSMITH_LLM_VALIDATE"
MODEL_ENV = "DIALOGSMITH_LLM_MODEL"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

COHERENCE_THRESHOLD = 0.5   # 0–1, below this the conversation is considered incoherent
QUALITY_THRESHOLD = 0.5     # 0–1, below this the sample is considered low-quality


def _should_validate():
    val = os.environ.get(VALIDATE_ENV, "").strip().lower()
    if val == "false":
        return False
    if val == "true":
        return True
    # Default: enable if API key is present
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _get_client():
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required for LLM validation. "
            "Install it with: pip install anthropic"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            f"Set {VALIDATE_ENV}=false to disable validation."
        )
    return anthropic.Anthropic(api_key=api_key)


def _format_conversation(turns):
    lines = []
    for turn in turns:
        role = turn.get("role", "unknown").upper()
        text = turn.get("text", "").strip()
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _score_sample(client, model, turns):
    """
    Ask the LLM to score a conversation sample.
    Returns (coherence: float, quality: float, reason: str).
    """
    conversation_text = _format_conversation(turns)

    prompt = f"""You are evaluating a conversation sample for use in fine-tuning a language model.

Rate the following conversation on two dimensions, each from 0.0 to 1.0:

1. coherence: Does this read as a natural, continuous conversation where each message follows logically from the previous? (0 = completely disjointed, 1 = perfectly coherent)
2. quality: Is this a meaningful, substantive exchange worth training on? Penalise one-word replies, pure greetings, or exchanges with no informational content. (0 = worthless, 1 = highly valuable)

Respond with ONLY a JSON object in this exact format:
{{"coherence": <float>, "quality": <float>, "reason": "<one sentence>"}}

Conversation:
{conversation_text}"""

    response = client.messages.create(
        model=model,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # The model may wrap the JSON in markdown fences or prose; extract the object.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")
    result = json.loads(match.group())
    return float(result["coherence"]), float(result["quality"]), result.get("reason", "")


def validate_samples(samples):
    """
    Validate a list of conversation samples.

    Each sample is a list of {"role": ..., "text": ...} dicts (as produced by telegram_extract.py).

    Returns filtered list of samples that pass validation.
    If validation is disabled or unavailable, returns all samples unchanged.
    """
    if not _should_validate():
        print("[validator] LLM validation disabled — skipping.")
        return samples

    try:
        client = _get_client()
    except (ImportError, EnvironmentError) as e:
        print(f"[validator] WARNING: {e}")
        print("[validator] Skipping LLM validation and returning all samples.")
        return samples

    model = os.environ.get(MODEL_ENV, DEFAULT_MODEL).strip()
    print(f"[validator] Running LLM validation with model: {model}")

    passed = []
    filtered = []

    for i, turns in enumerate(samples):
        try:
            coherence, quality, reason = _score_sample(client, model, turns)
        except Exception as e:
            print(f"[validator] Sample {i}: scoring failed ({e}), keeping sample.")
            passed.append(turns)
            continue

        if coherence < COHERENCE_THRESHOLD:
            filtered.append((i, "incoherent", coherence, quality, reason))
        elif quality < QUALITY_THRESHOLD:
            filtered.append((i, "low-quality", coherence, quality, reason))
        else:
            passed.append(turns)

    print(f"[validator] {len(passed)} passed, {len(filtered)} filtered out of {len(samples)} total.")

    if filtered:
        print("[validator] Filtered samples:")
        for idx, reason_type, coh, qual, reason in filtered:
            print(f"  sample {idx:4d} | {reason_type:12s} | coherence={coh:.2f} quality={qual:.2f} | {reason}")

    return passed
