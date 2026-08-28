"""Shared normalization helper for institution-name canonicalization (S9b fix #1).

Split into its own module (not inlined in build_institution_canonical.py) so
c09_validate_master.py / validate_master.py can import the SAME normalization function used to
build institution_name_canonical.csv, to check for un-flagged duplicate canonical names without
re-typing the logic.

Normalization is intentionally conservative and NEVER fuzzy: accent-fold, lowercase, punctuation
to spaces, drop a small fixed connector-word stoplist (universite/de/du/des/d/l/la/le/les/et/a),
sort the remaining tokens. Two raw strings that produce the same key are candidates for merging
ONLY when the merge is also checked against the dated university_merger_crosswalk.csv (a real
rename/merger must never be silently collapsed -- see build_institution_canonical.py).
"""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = {"universite", "university", "de", "du", "des", "d", "l", "la", "le", "les", "et", "a"}


def normalize_key(s: str) -> str:
    s2 = unicodedata.normalize("NFKD", s)
    s2 = "".join(c for c in s2 if not unicodedata.combining(c))
    s2 = s2.lower()
    s2 = re.sub(r"[^a-z0-9]+", " ", s2)
    toks = [t for t in s2.split() if t and t not in STOPWORDS]
    toks.sort()
    return " ".join(toks)
