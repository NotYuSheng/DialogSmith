"""Singapore (SG) sensitive-data detectors.

This is the reference locale module — copy it to add your own country.

A good locale detector is *precise*: a bare regex over chat text fires on
everything, so back it with a checksum/validator wherever the identifier has one
(see :func:`nric_valid`). High precision is what keeps the audit report
trustworthy instead of a wall of false positives.

CONTRIBUTING
------------
Add a country by creating ``ingest/redaction/<cc>.py`` (``cc`` = ISO 3166-1
alpha-2, lower-case), registering detectors with :func:`ingest.redaction.make`
and ``locale="<CC>"``, then importing it in ``ingest/redaction/__init__``.
Open items for SG that make good first contributions:
  * NRIC **M-series** (introduced 2022) uses a different checksum table — the
    regex below intentionally matches only S/T/F/G so it never flags an
    M-series number it can't verify. Add the M table + tests.
  * UEN (business registration number) detector.
"""

import re

from ingest.redaction import make

# NRIC/FIN checksum tables, indexed by (weighted_sum + offset) % 11.
_ST_SUFFIX = "JZIHGFEDCBA"  # S (citizen) and T (citizen, 2000+)
_FG_SUFFIX = "XWUTRQPNMLK"  # F and G (foreigner / long-term pass)
_WEIGHTS = (2, 7, 6, 5, 4, 3, 2)


def nric_valid(value: str) -> bool:
    """Validate a Singapore NRIC/FIN by its check digit (S/T/F/G series)."""
    value = value.strip().upper()
    if len(value) != 9:
        return False
    prefix, digits, suffix = value[0], value[1:8], value[8]
    if prefix not in "STFG" or not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits, _WEIGHTS))
    if prefix in "TG":  # T and G shift the weighted sum by 4
        total += 4
    table = _ST_SUFFIX if prefix in "ST" else _FG_SUFFIX
    return table[total % 11] == suffix


# Long form: full S/T/F/G + 7 digits + check letter, verified by checksum.
# Case-insensitive so "s1234567a" typed in lower-case is still caught (the
# validator upper-cases before checking).
make(
    "sg_nric",
    "NRIC/FIN",
    "SG",
    r"\b[STFG]\d{7}[A-Z]\b",
    severity="high",
    flags=re.IGNORECASE,
    validator=nric_valid,
)

# Short form: the last 3 digits + check letter (e.g. "123A"), the way people
# quote "the last 4 of my IC". It has no self-contained checksum and "123A"
# alone matches every block/unit number, so precision comes from REQUIRING an
# NRIC/IC/FIN keyword just before it. Only the ID span (named group) is
# reported, not the keyword.
make(
    "sg_nric_short",
    "NRIC/FIN (partial)",
    "SG",
    r"(?:nric|fin|\bic\b)\D{0,8}?(?P<id>(?<!\d)\d{3}[A-Za-z])\b",
    severity="medium",
    flags=re.IGNORECASE,
)

# Mobile (8/9), landline (6), VoIP (3): 8 digits, optional +65. Lookarounds keep
# it from grabbing 8-digit slices of longer number runs.
make(
    "sg_phone",
    "PHONE",
    "SG",
    r"(?<!\d)(?:\+?65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?!\d)",
    severity="medium",
)

# Postal code is 6 bare digits — far too noisy alone, so require an explicit
# "Singapore <code>", "S123456", or "S(123456)" context. The trailing lookahead
# stops it matching the first 6 digits of a longer token (e.g. the NRIC
# "S1234567D", which would otherwise read as "S123456").
make(
    "sg_postal",
    "POSTAL_CODE",
    "SG",
    r"(?:[Ss]ingapore\s+|\bS\(?)\d{6}\)?(?![\dA-Za-z])",
    severity="low",
)
