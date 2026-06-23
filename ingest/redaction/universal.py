"""Locale-independent detectors: same format the world over.

Email, payment cards, IP/MAC addresses, and vendor API keys don't change by
country, so they live here and always run. Country-specific catches (national
IDs, local phone formats, postal codes) belong in a per-locale module instead.
"""

import re

from ingest.redaction import UNIVERSAL, luhn_valid, make

# --- Contact / network -------------------------------------------------------

make(
    "email",
    "EMAIL",
    UNIVERSAL,
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    severity="medium",
)

make(
    "ipv4",
    "IP_ADDRESS",
    UNIVERSAL,
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
    severity="low",
)

make(
    "ipv6",
    "IP_ADDRESS",
    UNIVERSAL,
    r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b",
    severity="low",
)

make(
    "mac",
    "MAC_ADDRESS",
    UNIVERSAL,
    r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
    severity="low",
)

# --- Financial ---------------------------------------------------------------

# Broad 13–19 digit run (optionally space/dash grouped); Luhn rejects the noise.
make(
    "credit_card",
    "CARD_NUMBER",
    UNIVERSAL,
    r"\b(?:\d[ -]?){13,19}\b",
    severity="high",
    validator=luhn_valid,
)

# --- Secrets / credentials ---------------------------------------------------

make("openai_key", "API_KEY", UNIVERSAL, r"\bsk-[A-Za-z0-9]{20,}\b", severity="high")
make("aws_access_key", "API_KEY", UNIVERSAL, r"\bAKIA[0-9A-Z]{16}\b", severity="high")
make(
    "github_token",
    "API_KEY",
    UNIVERSAL,
    r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    severity="high",
)
make(
    "private_key_block",
    "PRIVATE_KEY",
    UNIVERSAL,
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    severity="high",
    flags=re.IGNORECASE,
)
