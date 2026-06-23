"""
Optional LLM-based conversation auditor.

Uses the shared OpenAI-compatible client (see :mod:`ingest.llm`), so it runs
against OpenAI or any local server. Controlled by the ``LLM_*`` environment
variables documented there (``LLM_VALIDATE``, ``LLM_API_BASE_URL``, ``LLM_MODEL``,
``LLM_API_KEY``).

Each conversation sample is audited on three axes:
  - coherence: does this read as a natural, continuous conversation?
  - quality:   is this a meaningful exchange worth training on?
  - pairing:   does each assistant turn actually respond to what came before?

Because the heuristic grouper can over-merge, the auditor may also *repair* a
sample by proposing split points rather than only keeping or dropping it:
  - action "keep":  use as-is
  - action "split": cut after the given turn indices into independent samples
  - action "drop":  discard entirely

A summary of every decision is printed so the user can audit the auditor.
"""

import json
import re

from ingest import llm

COHERENCE_THRESHOLD = 0.5   # below this the conversation is considered incoherent
QUALITY_THRESHOLD = 0.5     # below this the sample is considered low-quality
PAIRING_THRESHOLD = 0.5     # below this the turns don't respond to each other


def _format_conversation(turns):
    """Number every turn so the model can reference split points by index."""
    lines = []
    for i, turn in enumerate(turns):
        role = turn.get("role", "unknown").upper()
        text = turn.get("text", "").strip()
        lines.append(f"[{i}] {role}: {text}")
    return "\n".join(lines)


def _score_sample(client, model, turns):
    """Ask the LLM to audit a conversation sample.

    Returns a dict: coherence, quality, pairing (floats), action
    ("keep"|"split"|"drop"), split_after (list[int]), reason (str).
    """
    conversation_text = _format_conversation(turns)

    prompt = f"""You are auditing a conversation sample for fine-tuning a language model
to imitate the ASSISTANT speaker. The conversation was segmented by a heuristic
that can wrongly merge unrelated exchanges, so judge it carefully.

Each turn is numbered like "[i] ROLE: text".

Rate from 0.0 to 1.0:
1. coherence: does this read as one natural, continuous conversation?
2. quality: is this a meaningful exchange worth training on? Penalise pure
   greetings, one-word replies, and content-free chatter.
3. pairing: does each ASSISTANT turn actually respond to the USER turn(s) before
   it? (0 = replies are mismatched/non-sequiturs, 1 = every reply clearly fits)

Then choose an action:
- "keep": the sample is good as one conversation.
- "split": it is really two or more separate conversations. Give "split_after"
  as the list of turn indices AFTER which to cut (e.g. [3] cuts between turn 3
  and 4).
- "drop": it is not usable.

Respond with ONLY this JSON:
{{"coherence": <float>, "quality": <float>, "pairing": <float>,
  "action": "keep"|"split"|"drop", "split_after": [<int>...], "reason": "<one sentence>"}}

Conversation:
{conversation_text}"""

    raw = llm.chat(client, model, prompt, max_tokens=200)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")
    result = json.loads(match.group())
    return {
        "coherence": float(result["coherence"]),
        "quality": float(result["quality"]),
        "pairing": float(result.get("pairing", 1.0)),
        "action": str(result.get("action", "keep")).lower(),
        "split_after": [int(i) for i in result.get("split_after", []) or []],
        "reason": result.get("reason", ""),
    }


def _apply_split(turns, split_after):
    """Cut ``turns`` after each given index into independent samples."""
    cuts = sorted({i for i in split_after if 0 <= i < len(turns) - 1})
    if not cuts:
        return [turns]
    pieces, start = [], 0
    for idx in cuts:
        pieces.append(turns[start:idx + 1])
        start = idx + 1
    pieces.append(turns[start:])
    return [p for p in pieces if p]


def _has_both_roles(turns):
    roles = {t["role"] for t in turns}
    return "user" in roles and "assistant" in roles


def validate_samples(samples):
    """
    Audit a list of conversation samples.

    Each sample is a list of {"role": ..., "text": ...} dicts (as produced by
    ingest.core.build_samples).

    Returns the filtered/repaired list of samples. If validation is disabled or
    unavailable, returns all samples unchanged.
    """
    if not llm.should_validate():
        print("[validator] LLM validation disabled — skipping.")
        return samples

    try:
        client = llm.get_client()
    except (ImportError, EnvironmentError) as e:
        print(f"[validator] WARNING: {e}")
        print("[validator] Skipping LLM validation and returning all samples.")
        return samples

    model = llm.model()
    print(f"[validator] Auditing with model: {model} via {llm.endpoint_label()}")

    passed = []
    filtered = []
    split_count = 0

    for i, turns in enumerate(samples):
        try:
            r = _score_sample(client, model, turns)
        except Exception as e:
            print(f"[validator] Sample {i}: scoring failed ({e}), keeping sample.")
            passed.append(turns)
            continue

        low = (
            r["coherence"] < COHERENCE_THRESHOLD or
            r["quality"] < QUALITY_THRESHOLD or
            r["pairing"] < PAIRING_THRESHOLD
        )
        if r["action"] == "drop" or low:
            filtered.append((i, "dropped", r))
        elif r["action"] == "split":
            pieces = [p for p in _apply_split(turns, r["split_after"]) if _has_both_roles(p)]
            if pieces:
                passed.extend(pieces)
                split_count += 1
            else:
                filtered.append((i, "split-empty", r))
        else:
            passed.append(turns)

    print(
        f"[validator] {len(passed)} samples kept ({split_count} from splits), "
        f"{len(filtered)} dropped, from {len(samples)} input samples."
    )

    if filtered:
        print("[validator] Dropped samples:")
        for idx, kind, r in filtered:
            print(
                f"  sample {idx:4d} | {kind:11s} | "
                f"coh={r['coherence']:.2f} qual={r['quality']:.2f} pair={r['pairing']:.2f} "
                f"| {r['reason']}"
            )

    return passed
