"""Regex-based sensitive-data detection.

A *detector* is a named, locale-tagged regex (optionally backed by a checksum
validator) that flags one category of sensitive data — an email, a credit card,
a Singapore NRIC, etc. Detectors register themselves at import time via
:func:`register`, exactly like source adapters do, so adding coverage for a new
country is a single drop-in module under ``ingest/redaction/`` — no changes to
the scanner or the pipeline.

Detection is **non-destructive**: :func:`scan_text` and :func:`scan_samples`
only *report* matches (as :class:`Finding` objects). Whether to redact is the
user's decision, taken later against the audit report.

Want to add your country? Copy ``sg.py``, swap in your locale's patterns +
checksum validators, and register them. See ``CONTRIBUTING`` notes in ``sg.py``.
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Pattern

UNIVERSAL = "universal"  # locale tag for patterns that are the same worldwide


@dataclass(frozen=True)
class Detector:
    """One category of sensitive data and how to recognise it.

    Attributes:
        name: Unique id, e.g. ``"sg_nric"`` or ``"email"``.
        category: Human-facing label shown in reports, e.g. ``"NRIC"``.
        locale: ``"universal"`` or an ISO 3166-1 alpha-2 code (``"SG"``).
        pattern: Compiled regex. Every full match is a candidate.
        severity: ``"low" | "medium" | "high"`` — drives the suggested action.
        validator: Optional extra check on the matched string (e.g. Luhn,
            NRIC checksum). A candidate is only flagged if it returns True.
            This is what turns a noisy regex into a high-precision detector.
    """

    name: str
    category: str
    locale: str
    pattern: Pattern
    severity: str = "medium"
    validator: Optional[Callable[[str], bool]] = None


@dataclass(frozen=True)
class Finding:
    """A single detected span of sensitive data within one text."""

    detector: str
    category: str
    locale: str
    severity: str
    start: int
    end: int
    value: str
    preview: str  # masked, safe to print/log


_REGISTRY: "List[Detector]" = []


def register(detector: Detector) -> Detector:
    """Register a detector. Duplicate ``name`` is a programming error."""
    if any(d.name == detector.name for d in _REGISTRY):
        raise ValueError(f"Duplicate detector name: {detector.name!r}")
    _REGISTRY.append(detector)
    return detector


def make(
    name: str,
    category: str,
    locale: str,
    regex: str,
    *,
    severity: str = "medium",
    flags: int = 0,
    validator: Optional[Callable[[str], bool]] = None,
) -> Detector:
    """Compile a regex and register it as a detector in one call."""
    return register(
        Detector(
            name=name,
            category=category,
            locale=locale,
            pattern=re.compile(regex, flags),
            severity=severity,
            validator=validator,
        )
    )


def available_locales() -> "List[str]":
    return sorted({d.locale for d in _REGISTRY})


def iter_detectors(locales: Optional[Iterable[str]] = None) -> "List[Detector]":
    """Detectors for the given locales. ``None`` means all.

    ``UNIVERSAL`` detectors are always included — email/card/IP look the same
    everywhere, so they run regardless of which country was selected.
    """
    if locales is None:
        return list(_REGISTRY)
    wanted = {UNIVERSAL, *locales}
    return [d for d in _REGISTRY if d.locale in wanted]


def mask(value: str) -> str:
    """Mask a value for safe display in a report (keep shape, hide content)."""
    if "@" in value:  # email: keep first char + domain
        local, _, domain = value.partition("@")
        head = local[0] if local else ""
        return f"{head}***@{domain}"
    stripped = value.strip()
    if len(stripped) <= 4:
        return "*" * len(stripped)
    return f"{stripped[:2]}{'*' * (len(stripped) - 3)}{stripped[-1]}"


def scan_text(text: str, locales: Optional[Iterable[str]] = None) -> "List[Finding]":
    """Return all sensitive-data findings in ``text`` (non-destructive)."""
    findings: List[Finding] = []
    for det in iter_detectors(locales):
        # A detector may match surrounding context but expose only the sensitive
        # span via a named ``id`` group (e.g. require "NRIC" before the number,
        # but report just the number). Otherwise the whole match is the value.
        report_id = "id" in det.pattern.groupindex
        for m in det.pattern.finditer(text):
            value = m.group("id") if report_id else m.group()
            if det.validator and not det.validator(value):
                continue
            start, end = m.span("id") if report_id else m.span()
            findings.append(
                Finding(
                    detector=det.name,
                    category=det.category,
                    locale=det.locale,
                    severity=det.severity,
                    start=start,
                    end=end,
                    value=value,
                    preview=mask(value),
                )
            )
    return findings


def luhn_valid(number: str) -> bool:
    """Luhn checksum — filters most non-card digit runs (phone/IDs/etc)."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Importing the package registers the bundled detectors. Add a new locale module
# here (and as a file) and its detectors light up everywhere automatically.
from ingest.redaction import universal as _universal  # noqa: E402,F401
from ingest.redaction import sg as _sg  # noqa: E402,F401
