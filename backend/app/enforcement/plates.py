"""Indian vehicle registration number parsing, validation and OCR correction.

Supported formats (spaces / dashes ignored):

* Standard:  ``SS DD L{1,3} NNNN``  e.g. ``KA 01 AB 1234``, ``DL 3C AB 1234``
* Bharat (BH) series: ``YY BH NNNN L{1,2}`` e.g. ``22 BH 1234 AB``

OCR engines confuse look-alike characters (O/0, I/1, B/8, S/5 ...).  The
:func:`normalize` function tries every valid segmentation of the raw string
and coerces characters into the class required at each position, returning
the candidate needing the fewest substitutions.  The number of substitutions
is reported so the caller can lower its confidence accordingly.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR",
    "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR",
    "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "TG", "UK", "UA", "UP", "WB",
}
TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "J": "1", "T": "7",
            "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4"}
TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A", "7": "T"}

STANDARD_RE = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})$")
BH_RE = re.compile(r"^(\d{2})(BH)(\d{4})([A-Z]{1,2})$")
MAX_CORRECTIONS = 2  # more substitutions than this is guessing, not correcting


@dataclass
class PlateParse:
    number: str           # canonical, no spaces: KA01AB1234
    formatted: str        # display: KA 01 AB 1234
    kind: str             # "standard" | "bh"
    corrections: int      # substitutions made to fit the format
    raw: str


def clean(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def _coerce(text: str, pattern: str) -> Optional[Tuple[str, int]]:
    """Coerce ``text`` to the class pattern (``L``=letter, ``D``=digit)."""
    out, fixes = [], 0
    for ch, cls in zip(text, pattern):
        if cls == "D":
            if ch.isdigit():
                out.append(ch)
            elif ch in TO_DIGIT:
                out.append(TO_DIGIT[ch])
                fixes += 1
            else:
                return None
        else:
            if ch.isalpha():
                out.append(ch)
            elif ch in TO_LETTER:
                out.append(TO_LETTER[ch])
                fixes += 1
            else:
                return None
    return "".join(out), fixes


def _candidates(text: str) -> List[PlateParse]:
    n, found = len(text), []
    for rto in (2, 1):
        for series in (2, 1, 3):
            pattern = "LL" + "D" * rto + "L" * series + "DDDD"
            if len(pattern) != n:
                continue
            res = _coerce(text, pattern)
            if not res or res[0][:2] not in STATE_CODES:
                continue
            num, fixes = res
            m = STANDARD_RE.match(num)
            if m and fixes <= MAX_CORRECTIONS and int(m.group(2)) > 0 and m.group(4) != "0000":
                found.append(PlateParse(num, " ".join(m.groups()), "standard", fixes, text))
    for series in (2, 1):
        pattern = "DD" + "LL" + "DDDD" + "L" * series
        if len(pattern) == n and text[2:4] in ("BH", "8H", "B4"):
            res = _coerce(text, pattern)
            if res and res[0][2:4] == "BH" and res[1] <= MAX_CORRECTIONS:
                m = BH_RE.match(res[0])
                if m:
                    found.append(PlateParse(res[0], " ".join(m.groups()), "bh", res[1], text))
    return found


def normalize(raw: str) -> Optional[PlateParse]:
    """Best valid Indian registration for ``raw`` or ``None``."""
    text = clean(raw)
    if not 6 <= len(text) <= 11:
        return None
    cands = _candidates(text)
    if not cands:
        return None
    # fewest corrections; prefer 2-digit RTO / 2-letter series (most common)
    return min(cands, key=lambda c: (c.corrections, len(c.number) != 10))


def is_valid(number: str) -> bool:
    p = normalize(number)
    return bool(p and p.corrections == 0)


def format_plate(number: str) -> str:
    p = normalize(number)
    return p.formatted if p else clean(number)
