"""Region name canonicalisation. Kept in its own importable module so it is unit-testable (the
05 pipeline script runs top-to-bottom on import and cannot be imported in a test).

The failure this fixes: geo.api.gouv.fr returns 'Provence-Alpes-Côte d'Azur' with a CURLY apostrophe
(U+2019) while the dashboard fallback uses a STRAIGHT one (U+0027); a normaliser that only strips
accents leaves them as two distinct keys, so the region rollup showed the region twice. Junk values
('None', 'nan', '-', 'NC') were also leaking through as if they were real regions.

COPY-IN NOTE (Phase C, 2026-08-27): copied verbatim from
V2\\scripts\\region.py (read-only, checksummed in staged/checksums.json) per the standalone
project principle -- this run never imports across the RUN/V2 boundary at runtime. Reused here
for its `canon_region` function and, importantly, its `_CANON_NAMES` canonical region-name list,
which c05_region.py indexes into directly so every region string this Phase C build emits is
byte-identical (same accents, same apostrophe style) to what the rest of the V2 pipeline already
uses and validated -- no accented French text is retyped by hand anywhere in this build.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

_CANON_NAMES = [
    "Île-de-France", "Auvergne-Rhône-Alpes", "Occitanie", "Provence-Alpes-Côte d'Azur",
    "Nouvelle-Aquitaine", "Grand Est", "Bretagne", "Pays de la Loire", "Hauts-de-France",
    "Normandie", "Bourgogne-Franche-Comté", "Centre-Val de Loire", "Corse",
    "Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte",
]
_NULL = {"", "none", "nan", "-", "nc", "autrenc"}


def region_key(value) -> str:
    """Strip accents AND all punctuation/spacing so apostrophe (straight vs curly) and hyphen variants
    collapse to a single key. "Provence-Alpes-Côte d'Azur" -> "provencealpescotedazur"."""
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", ascii_value)


_CANON = {region_key(name): name for name in _CANON_NAMES}


def canon_region(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    key = region_key(value)
    if key in _NULL:
        return None
    return _CANON.get(key, value)
