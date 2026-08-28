"""Link a resolved lab NAME to an RNSR structure id (for OpenAlex/v1 candidates, which lack rnsr_id;
HAL candidates already carry rnsr_id from HAL's structure referential). Deterministic, no network/model.

Match order (strongest first): unit code (UMR/UAR/UMS/UPR/… + number) exact → lab acronym == RNSR sigle
→ normalized-token Jaccard on the libellé, with city breaking ties. RNSR active carries
numero_national_de_structure, libelle, sigle, label_numero (unit code), commune, tutelles.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

_STOP = {"de", "la", "le", "les", "des", "du", "et", "d", "l", "en", "aux", "a", "pour", "sur", "the", "of"}
_UNIT = "umr|uar|ums|upr|usr|uor|umi|fre|gdr|ea|ur|erl|fr"
_CODE_RE = re.compile(rf"\b({_UNIT})\s*[_-]?\s*(\d{{3,4}})\b", re.I)

# Place discriminators that must NOT be introduced by a fuzzy name match unless the query (or the
# provided city) already carries them. This defeats the "Institut Pasteur" -> "Institut Pasteur de la
# Guadeloupe" class of bug: a bare parent-institution name token-matches a geographically-specialised
# sub-structure and silently exports the grant to the wrong (often overseas) region. Overseas +
# strongly-discriminating region tokens only — mainland city tokens are left out on purpose so we
# never over-reject a legitimate "... Paris-Seine"-style unit whose place token is already in the name.
_PLACE_DISCRIMINATORS = {
    "guadeloupe", "guyane", "martinique", "reunion", "mayotte", "caledonie", "polynesie",
    "tahiti", "moorea", "noumea", "papeete", "cayenne", "corse", "corsica",
}


def _norm(value) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", ascii_value.lower())).strip()


def _tokens(value) -> set[str]:
    return {t for t in _norm(value).split() if t not in _STOP and len(t) > 1}


def _code(value) -> str | None:
    m = _CODE_RE.search(str(value))
    return f"{m.group(1).lower()}{m.group(2)}" if m else None


def _sigle(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _first_col(df: pd.DataFrame, names: list[str]) -> str | None:
    return next((n for n in names if n in df.columns), None)


def build_index(active: pd.DataFrame) -> dict:
    lib_col = _first_col(active, ["libelle", "label"])
    id_col = _first_col(active, ["numero_national_de_structure", "rnsr", "numero"])
    code_col = _first_col(active, ["label_numero", "code_unite"])
    sigle_col = _first_col(active, ["sigle"])
    commune_col = _first_col(active, ["commune", "ville"])
    by_code, by_sigle, rows = {}, {}, []
    for r in active.itertuples(index=False):
        rid = getattr(r, id_col, None) if id_col else None
        if not rid:
            continue
        code = _code(getattr(r, code_col, "")) if code_col else None
        if code and code not in by_code:
            by_code[code] = rid
        sig = _sigle(getattr(r, sigle_col, "")) if sigle_col else ""
        if len(sig) >= 3 and sig not in by_sigle:
            by_sigle[sig] = rid
        rows.append((rid, _tokens(getattr(r, lib_col, "") if lib_col else ""),
                     _norm(getattr(r, commune_col, "") if commune_col else "")))
    return {"by_code": by_code, "by_sigle": by_sigle, "rows": rows}


def match_lab(lab_name: str, city, index: dict, threshold: float = 0.5) -> str | None:
    if not lab_name or pd.isna(lab_name):
        return None
    code = _code(lab_name)
    if code and code in index["by_code"]:
        return index["by_code"][code]
    # a parenthesised or standalone acronym in the lab name matching an RNSR sigle
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", str(lab_name)):
        sig = _sigle(tok)
        if len(sig) >= 3 and sig in index["by_sigle"]:
            return index["by_sigle"][sig]
    lab_tokens = _tokens(lab_name)
    if not lab_tokens:
        return None
    city_norm = _norm(city) if city and not pd.isna(city) else ""
    best_id, best_score = None, threshold
    for rid, lib_tokens, commune in index["rows"]:
        if not lib_tokens:
            continue
        # Place-discriminator guard: if the candidate libellé introduces an overseas/region token that
        # the query lab name does NOT carry, only accept it when the provided city actually matches the
        # candidate's commune. Prevents a bare parent-institution name (e.g. "Institut Pasteur") from
        # token-matching a geographically specialised sub-structure ("...de la Guadeloupe") and
        # exporting the grant off-region. (If the place token is already in the lab name it is not
        # "extra", so genuinely overseas units still match.)
        extra_place = (lib_tokens - lab_tokens) & _PLACE_DISCRIMINATORS
        if extra_place and not (city_norm and commune and city_norm in commune):
            continue
        score = len(lab_tokens & lib_tokens) / len(lab_tokens | lib_tokens)
        if city_norm and commune and city_norm in commune:
            score += 0.1
        if score > best_score:
            best_id, best_score = rid, score
    return best_id


def apply_links(resolutions: pd.DataFrame, active: pd.DataFrame) -> pd.DataFrame:
    if resolutions.empty or active.empty:
        return resolutions
    index = build_index(active)
    out = resolutions.copy()
    if "rnsr_id" not in out.columns:
        out["rnsr_id"] = None
    need = out.rnsr_id.isna()
    city_series = out["city"] if "city" in out.columns else pd.Series(None, index=out.index)
    for i in out.index[need]:
        out.at[i, "rnsr_id"] = match_lab(out.at[i, "lab_name"], city_series.get(i), index)
    return out
