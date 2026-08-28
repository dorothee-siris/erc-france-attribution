"""c11: re-link the v2-inherited RNSR errors found by the S9a hostile data review.

NEW FILE (2026-08-28). Read-only against the master, c08, and every existing c00-c10 script --
imports their helpers unmodified. Writes ONLY under RUN/staged/v2_relink/. Never touches
deliverable/erc_france_attribution_master.* or any c00-c10 script (c08 is being edited by another
worker and will integrate this script's overrides.csv itself).

Deterministic, local-only (no web). ASCII-only console output (aprint, matches every other c0x
script's Windows-cp1252-safe convention).

--------------------------------------------------------------------------------------------------
BACKGROUND (see reports/S9a_hostile_data_review.md for the full argument; this header only
summarizes the mechanism this script exists to fix):

  The master's grade-A/B rows (983 of them) carry an `rnsr_id` inherited VERBATIM from v2's own
  french_components.parquet, auto-accepted without re-audit (`match_mode` is null on every one of
  them, F27). Several classes of v2-era linking defect are known:

  (a) CEA "Direction des Energies" (rnsr_id 202024262P) is an administrative directorate, not a
      lab -- it has become a catch-all SINK for 55 components / 50 distinct labs (F23).
  (b) 148 v2-bucketed rows link to an RNSR record whose libelle shares no significant text with
      the published lab_name (F26) -- untriaged.
  (c) 948358:0 "Laboratoire de Mathematiques d'Orsay" was captured by a same-named-prefix RNSR
      record in Savoie ("Laboratoire de mathematiques", LAMA) because the distinguishing token
      "d'Orsay" was dropped by normalization (F24).
  (d) 693762:0 "Laboratory of Human Lymphohematopoiesis" (evidence unit_id "INSERM UMR 1163") was
      resolved against INRA's OWN "UMR 1163" numbering (a different organism's numbering scheme
      that happens to share the bare digit sequence) instead of INSERM's own U/UMR_S convention
      (F1).
  (e) 101161432:0 (CREST-ENSAI) keeps the correct rnsr_id (CREST IS UMR 9194) but the REGION was
      taken from the RNSR record's Palaiseau headquarters address instead of the researched
      Rennes/ENSAI site (F3) -- the RTO/HQ effect re-entering one layer down.
  (f) 852448:0 (Centre Marc Bloch) keeps the correct rnsr_id (it IS the Berlin Franco-German UMIFRE)
      but Berlin's postal code 10117 was parsed as if French (departement "10" = Aube, a REAL
      French departement code, so a pure digit-plausibility check cannot catch this -- only a
      commune-name check can) (F17).

  This script's job is to (1) identify the full suspect set with generic, reusable detectors, (2)
  re-run the guarded, NEVER-FUZZY match ladder (rnsr_match.RnsrIndex, unmodified) against the TRUE
  lab_name for every suspect, using whatever independent city evidence is actually available, (3)
  apply the two hard rules the task spec adds on top of the existing ladder -- an organism-name
  prefix constrains which numbering convention is tried, and a city token embedded in lab_name (or
  in the original evidence) beats the RNSR record's own headquarters address -- and (4) write the
  results as staged overrides for c08 to integrate, NEVER editing the master directly.
--------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from common_io import RUN, RNSR_DIR, V2, REVIEW_ROOT, STAGED, aprint  # noqa: E402
import rnsr_match as rm  # noqa: E402
from rnsr_match import RnsrIndex  # noqa: E402
from evidence_hints import named_tutelle_match, same_department  # noqa: E402 (unmodified reuse)
from institution_canon import normalize_key  # noqa: E402
from region import canon_region  # noqa: E402
from c05_region import DEPT_TO_REGION, CITY_DEPT, dept_from_postal, _norm_city  # noqa: E402
from tutelle_align import (  # noqa: E402
    build_name_nature_dict, build_sigle_name_dict, build_sigle_nature_dict,
)
from c10_helpers import tutelles_for_row, load_crosswalk_events, apply_crosswalk  # noqa: E402
from c06_gates_and_outputs import joinlist  # noqa: E402

OUT_DIR = STAGED / "v2_relink"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT = OUT_DIR / "RELINK_CHECKPOINT.md"

MASTER_PARQUET = RUN / "deliverable" / "erc_france_attribution_master.parquet"
FC_PARQUET = V2 / "outputs" / "french_components.parquet"
EVIDENCE_PROV_CSV = V2 / "outputs" / "evidence_provenance.csv"
SOURCE_COMPONENTS_DIR = REVIEW_ROOT / "runs" / "20260809T141414Z" / "components"

# =====================================================================================
# Detector thresholds (documented, conservative; see RELINK_CHECKPOINT.md calibration log)
# =====================================================================================
TOKEN_MISMATCH_JACCARD_MAX = 0.15
TOKEN_MISMATCH_SEQ_MAX = 0.40
SINK_MIN_COMPONENTS = 8
SINK_AVG_JACCARD_MAX = 0.15

# Six rows the task requires an explicit, individually-verified outcome for (four named in the
# task prose + two more required by the final-JSON output schema). These are NOT hardcoded to a
# specific new rnsr_id -- each is fed through the SAME generic attempt_relink()/compute_region()
# pipeline as every other suspect, using whatever independent evidence is available for it
# (SOURCE_COMPONENTS_DIR's original unit_id+city for the two Phase-C-local rows, french_components'
# own researched city for the v2-inherited ones, and the embedded-city-in-lab_name hard constraint
# as the last resort) -- verified by hand against the RNSR active.parquet rows during design (see
# RELINK_CHECKPOINT.md) to confirm the generic machinery lands on the correct answer for each.
NAMED_ROW_IDS = ["948358:0", "693762:0", "101161432:0", "852448:0", "856455:0", "805256:0"]

# Hand-verified, narrow denylist of foreign commune names encountered in this dataset (NOT an
# exhaustive gazetteer -- same "targeted, not exhaustive" convention as c05_region.py's own
# CITY_DEPT). A 5-digit postal code can coincide with a real French departement number (e.g.
# Berlin 10117 -> "10" = Aube) so digit-plausibility alone cannot catch a foreign site; only a
# commune-name check can.
FOREIGN_CITY_DENYLIST = {"berlin"}

# Extra city -> departement entries needed for THIS suspect population, on top of c05_region's own
# CITY_DEPT (built for the main Phase C run's own researched-city field). Every entry hand-verified
# as a single, unambiguous French commune. Source: reports/S9a_hostile_data_review.md F23 table
# (the true location of the 31 confirmed-mislocated CEA-sink labs) plus a handful of cities that
# appear embedded in mismatch-set lab_name text.
EXTRA_CITY_DEPT: dict[str, str] = {
    "orsay": "91", "palaiseau": "91", "evry": "91",
    "saint martin d heres": "38", "bron": "69", "villeurbanne": "69",
    "castanet tolosan": "31", "vandoeuvre les nancy": "54", "nancy": "54",
    "amiens": "80", "poitiers": "86",
}


# rnsr_match.norm_text and c05_region._norm_city both transliterate to ASCII via
# unicodedata.normalize("NFKD", ...).encode("ascii", "ignore") -- a CURLY apostrophe (U+2019, the
# character web-sourced text like "Laboratoire de Mathematiques d'Orsay" actually uses) has no
# ASCII-compatible NFKD decomposition, so it is silently DROPPED rather than replaced with a
# separator, fusing "d" and "Orsay" into one word ("dorsay") and defeating any word-boundary city
# search or libelle-containment test on the fused string. Cannot fix rnsr_match.py/c05_region.py
# themselves (existing scripts, read-only per the task boundary) -- so every text THIS script feeds
# into their functions is pre-cleaned here: curly quotes/dashes -> their straight ASCII equivalents,
# which their own existing regexes (`[^a-z0-9]+` -> space) then correctly turn into a separator.
_PUNCT_NORMALIZE = str.maketrans({
    "’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', " ": " ", "–": "-", "—": "-",
})


def clean_text(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return s
    return str(s).translate(_PUNCT_NORMALIZE)


COMBINED_CITY_DEPT: dict[str, str] = {**EXTRA_CITY_DEPT, **CITY_DEPT}
_CITY_KEYS_BY_LEN = sorted(COMBINED_CITY_DEPT.keys(), key=len, reverse=True)


def find_city_key(text) -> str | None:
    """Word-boundary substring search for a known city name inside ANY text -- a bare city name,
    a full researched address ('5 Rue Rene Descartes 67084 STRASBOURG CEDEX'), or a lab_name that
    embeds a city token ('Laboratoire de Mathematiques d'Orsay'). Only keys >=4 chars are tried
    (avoids short-token noise). This is the single normalization path used both for parsing a
    hint_city value and for task rule 2's 'city token embedded in lab_name is a hard constraint'."""
    nt = _norm_city(text)
    if not nt:
        return None
    for key in _CITY_KEYS_BY_LEN:
        if len(key) < 4:
            continue
        if re.search(rf"\b{re.escape(key)}\b", nt):
            return key
    return None


def city_dept(city) -> str | None:
    key = find_city_key(city)
    return COMBINED_CITY_DEPT.get(key) if key else None


def extract_embedded_city(lab_name) -> str | None:
    """Task rule 2: a city token embedded in lab_name itself ('d'Orsay', 'de Marseille', 'de
    Bordeaux'...) is a hard constraint, independent by construction (it is part of the published,
    true lab_name text). Returns the matched, normalized city key (usable as a hint_city input to
    the same ladder every other ranking uses) or None."""
    return find_city_key(lab_name)


# Hand-curated hint city for the 31/55 CEA-sink components whose true location the hostile review
# already established (S9a F23 table) by comparing each lab_name against its OWN, unambiguous RNSR
# record elsewhere in the corpus -- a local, already-produced, already-vetted document (reading it
# is not "web"). Used only as the `hint_city` input to the SAME guarded ladder every other suspect
# goes through -- it does not itself assign an rnsr_id.
SINK_CITY_HINTS: dict[str, str] = {}
for _cid in ("856555:0", "101142154:0", "101289316:0"):
    SINK_CITY_HINTS[_cid] = "Grenoble"
for _cid in ("101126009:0", "101164392:0"):
    SINK_CITY_HINTS[_cid] = "Saint Martin d Heres"
for _cid in ("101071777:0", "885746:0", "758473:0", "101116110:0"):
    SINK_CITY_HINTS[_cid] = "Bron"
for _cid in ("101200669:0", "963976:0"):
    SINK_CITY_HINTS[_cid] = "Marseille"
SINK_CITY_HINTS["834195:0"] = "Nice"
for _cid in ("101119058:0", "771793:0", "832889:0", "101069259:0"):
    SINK_CITY_HINTS[_cid] = "Toulouse"
for _cid in ("948688:0", "101170500:0", "803004:0"):
    SINK_CITY_HINTS[_cid] = "Montpellier"
SINK_CITY_HINTS["951444:0"] = "Castanet Tolosan"
SINK_CITY_HINTS["101124066:0"] = "Nantes"
SINK_CITY_HINTS["101170736:0"] = "Strasbourg"
for _cid in ("724705:0", "825404:0"):
    SINK_CITY_HINTS[_cid] = "Vandoeuvre les Nancy"
SINK_CITY_HINTS["101221746:0"] = "Rennes"
for _cid in ("101117070:0", "101244668:0"):
    SINK_CITY_HINTS[_cid] = "Poitiers"
SINK_CITY_HINTS["101040391:0"] = "Bordeaux"
SINK_CITY_HINTS["101069244:0"] = "Amiens"
SINK_CITY_HINTS["101001097:0"] = "Lyon"
for _cid in ("963840:0", "101247370:0"):
    SINK_CITY_HINTS[_cid] = "Lyon"
SINK_HINT_SOURCE_NOTE = "reports/S9a_hostile_data_review.md F23 table (31 confirmed-mislocated sink labs)"

# Organism-numbering-convention table (narrow, hand-verified, same spirit as c10_helpers.py's own
# ACRONYM_EXPANSIONS): some organisms code the SAME unit number under a different RNSR label_numero
# prefix than the generic bare "UMR" -- INSERM units are "U<n>"/"UMR_S<n>", never bare "UMR<n>".
# When evidence text names an organism explicitly alongside a bare numeric code, this rung ALSO
# tries that organism's own known prefix(es) for the SAME digit sequence (still an EXACT code
# match on the number -- never a fuzzy name match, exactly the precedent set by evidence_hints.py's
# own numeric-fallback rung) and, if that alone is not unique, additionally requires the named
# organism to appear verbatim in the candidate's own `tutelles` field (evidence_hints.named_tutelle_match,
# unmodified) before accepting a winner.
ORGANISM_CODE_ALIASES: dict[str, tuple[list[str], str]] = {
    "inserm": (["U", "UMRS"], "sante et de la recherche medicale"),
}


def detect_organism_and_digits(unit_id_text) -> tuple[str | None, str | None, list[str]]:
    if not unit_id_text:
        return None, None, []
    nt = rm.norm_text(unit_id_text)
    digits = re.findall(r"\d{2,5}", str(unit_id_text))
    for kw, (aliases, tutelle_substr) in ORGANISM_CODE_ALIASES.items():
        if re.search(rf"\b{kw}\b", nt):
            return kw, tutelle_substr, digits
    return None, None, digits


def match_unit_id_organism_aware(unit_id_text, index: RnsrIndex, active_by_id) -> tuple[str | None, str | None]:
    organism, tutelle_substr, digits = detect_organism_and_digits(unit_id_text)
    if not organism or not digits:
        return None, None
    aliases = ORGANISM_CODE_ALIASES[organism][0]
    candidate_codes = {f"{prefix}{d}" for d in digits for prefix in aliases}
    ids: set[str] = set()
    for cc in candidate_codes:
        ids |= index.code_index.get(cc, set())
    if len(ids) == 1:
        return next(iter(ids)), "unit_id_organism_code_convention"
    if len(ids) > 1:
        filtered = set()
        for sid in sorted(ids):
            arow = active_by_id.loc[sid]
            if isinstance(arow, pd.DataFrame):
                arow = arow.iloc[0]
            if named_tutelle_match(tutelle_substr, arow.get("tutelles")):
                filtered.add(sid)
        if len(filtered) == 1:
            return next(iter(filtered)), "unit_id_organism_code_convention_tutelle_filtered"
    return None, None


def match_whole_name_as_sigle(lab_name, city, index: RnsrIndex, active_by_id) -> tuple[str | None, str | None]:
    """Exact rung: the FULL lab_name, once punctuation/case-stripped, equals an RNSR record's own
    `sigle` field similarly stripped ('Centre Marc Bloch' vs sigle 'CENTRE MARC BLOCH') -- not a
    fuzzy match, a literal equality test on the normalized whole string. rnsr_match.extract_acronyms
    only pulls single fancy-cased tokens or parenthesised text out of lab_name, so it never tries
    lab_name AS a sigle candidate in its own right; this rung fills that gap. Requires city
    corroboration (same standard as every other city-gated rung) to guard against a short/generic
    lab_name coincidentally equalling an unrelated sigle."""
    sig = rm.norm_sigle(lab_name)
    if len(sig) < 3:
        return None, None
    ids = index.sigle_index.get(sig, set())
    if len(ids) != 1 or not city:
        return None, None
    sid = next(iter(ids))
    arow = active_by_id.loc[sid]
    if isinstance(arow, pd.DataFrame):
        arow = arow.iloc[0]
    if rm.cities_corroborate(city, arow.get("commune")) or same_department(city, arow.get("code_postal")):
        return sid, "whole_name_equals_sigle_city"
    return None, None


def attempt_relink(lab_name, hint_city, unit_id_text, index: RnsrIndex, active_by_id):
    """Guarded ladder for ONE suspect row. Returns (rnsr_id|None, match_mode|None,
    independently_corroborated: bool). Never fuzzy: every rung is an exact code match, an exact
    sigle match, or an exact/substring libelle match, each gated the same way rnsr_match.py's own
    RnsrIndex.link() gates them -- this just tries more inputs (unit_id_text if we have real
    evidence for it, and the free-text lab_name itself, which sometimes embeds a UMR/EA/UMS code)
    before falling back to the same uniqueness-without-city rung the base ladder already has."""
    if unit_id_text:
        sid, mode = match_unit_id_organism_aware(unit_id_text, index, active_by_id)
        if sid:
            return sid, mode, True
        sid, mode = index.match_unit_id(unit_id_text)
        if sid:
            return sid, mode, True

    sid, mode = index.match_unit_id(lab_name)
    if sid:
        return sid, mode, True

    if hint_city:
        sid, mode = match_whole_name_as_sigle(lab_name, hint_city, index, active_by_id)
        if sid:
            return sid, mode, True
        sid, mode = index.match_sigle_city(lab_name, hint_city)
        if sid:
            return sid, mode, True
        sid, mode = index.match_libelle_city(lab_name, hint_city)
        if sid:
            return sid, mode, True

    sid, mode = index.match_unique_no_city(lab_name)
    if sid:
        if hint_city:
            arow = active_by_id.loc[sid]
            if isinstance(arow, pd.DataFrame):
                arow = arow.iloc[0]
            if rm.cities_corroborate(hint_city, arow.get("commune")) or same_department(hint_city, arow.get("code_postal")):
                return sid, mode + "_city_corroborated", True
            return None, "unique_no_city_contradicted_by_hint_city", False
        return sid, mode, False

    return None, None, False


def compute_region(new_rnsr_id, hint_city, hint_city_independent, active_by_id):
    """Region priority chain for a re-linked row: RNSR postal (if the RNSR record's own address is
    plausibly French) unless an independently-evidenced city contradicts it, in which case the
    evidence city wins (task rule 2: 'the researched/evidence city beats the RNSR headquarters
    address when they conflict') and hq_address_overridden is flagged. A French-postal check
    (5 digits AND a plausible departement 01-95/2A/2B/97x AND the commune name itself is not on the
    hand-verified foreign-city denylist) gates every RNSR-derived region; a record that fails it
    gets region=None + foreign_postal_code, never a guessed region (task rule 3)."""
    flags: list[str] = []
    rnsr_commune = rnsr_cp = None
    if new_rnsr_id is not None and new_rnsr_id in active_by_id.index:
        arow = active_by_id.loc[new_rnsr_id]
        if isinstance(arow, pd.DataFrame):
            arow = arow.iloc[0]
        rnsr_commune, rnsr_cp = arow.get("commune"), arow.get("code_postal")

    rnsr_is_french = True
    if rnsr_commune is not None and _norm_city(rnsr_commune) in FOREIGN_CITY_DENYLIST:
        rnsr_is_french = False
        flags.append("foreign_postal_code")

    dept_rnsr, corse_flag = dept_from_postal(rnsr_cp)
    if corse_flag == "corse_postal_ambiguous":
        flags.append("ambiguous_corse_postal")
    rnsr_postal_plausible = bool(dept_rnsr) and dept_rnsr in DEPT_TO_REGION

    dept_hint = city_dept(hint_city) if hint_city else None

    region = source = cp_out = None
    if hint_city_independent and dept_hint and (not rnsr_postal_plausible or not rnsr_is_french or dept_hint != dept_rnsr):
        region = DEPT_TO_REGION.get(dept_hint)
        source = "evidence_city"
        if rnsr_postal_plausible and rnsr_is_french and dept_hint != dept_rnsr:
            flags.append("hq_address_overridden")
    elif rnsr_is_french and rnsr_postal_plausible:
        region = DEPT_TO_REGION.get(dept_rnsr)
        source = "rnsr_postal"
        cp_out = rnsr_cp
    elif not rnsr_is_french:
        region, source, cp_out = None, None, None
    elif dept_hint:
        region = DEPT_TO_REGION.get(dept_hint)
        source = "evidence_city"

    region = canon_region(region)
    return region, source, cp_out, rnsr_commune, rnsr_cp, flags


def load_source_component_evidence() -> dict[str, dict]:
    """Original per-component evidence (unit_id/city/lab_name), read-only, from the Phase-C source
    batch (SOURCE_COMPONENTS_DIR). Covers only the rows this run's own c02 built locally (grade C /
    match_mode not null) -- the v2-inherited 983 have no file here (confirmed: v2's own
    french_components.parquet is a SEPARATE, independent evidence trail, read separately below)."""
    out: dict[str, dict] = {}
    if not SOURCE_COMPONENTS_DIR.exists():
        return out
    for p in sorted(SOURCE_COMPONENTS_DIR.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cid = rec.get("component_id")
        if cid:
            out[cid] = rec
    return out


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def token_mismatch_score(lab_name, libelle) -> tuple[float, float]:
    ta, tb = set(normalize_key(str(lab_name or "")).split()), set(normalize_key(str(libelle or "")).split())
    j = jaccard(ta, tb)
    seq = difflib.SequenceMatcher(None, normalize_key(str(lab_name or "")), normalize_key(str(libelle or ""))).ratio()
    return j, seq


def checkpoint(msg: str) -> None:
    with open(CHECKPOINT, "a", encoding="utf-8") as f:
        f.write(f"\n- {msg}")
    aprint("[checkpoint]", msg)


# =====================================================================================
# Independent-evidence-city resolution, priority order (highest-trust first). Each rung is
# documented at the point of use; see module docstring section (e)/(f) for why master.city is
# NOT trustworthy on its own for v2-inherited rows (it is frequently just the WRONG RNSR record's
# own commune, copied through, not independent evidence -- confirmed by hand for 948358:0 during
# design: master.city == the Savoie LAMA's own commune string, byte for byte).
# =====================================================================================

def resolve_hint_city(cid, lab_name, is_phase_c_local, master_city, fc_city, src_evidence) -> tuple[str | None, bool, str | None]:
    rec = src_evidence.get(cid)
    if rec and rec.get("city"):
        return rec["city"], True, "source_component_json"
    if fc_city is not None and str(fc_city).strip() and str(fc_city).lower() != "nan":
        return str(fc_city), True, "french_components_city"
    if cid in SINK_CITY_HINTS:
        return SINK_CITY_HINTS[cid], True, "s9a_report_table"
    if is_phase_c_local and master_city is not None and str(master_city).strip() and str(master_city).lower() != "nan":
        return str(master_city), True, "master_city_phase_c_local"
    embedded = extract_embedded_city(lab_name)
    if embedded:
        return embedded, True, "embedded_in_lab_name"
    return None, False, None


def resolve_unit_id_text(cid, src_evidence) -> str | None:
    """Original evidence unit_id, read-only, ONLY for the Phase-C-local rows that have a source
    JSON (v2-inherited rows never do -- their own numbering scheme collisions are exactly what
    this run is fixing, and there is no comparable raw-evidence file to recover a unit_id from
    for them; they rely on match_unit_id(lab_name) picking up an EMBEDDED code instead)."""
    rec = src_evidence.get(cid)
    return rec.get("unit_id") if rec else None


# =====================================================================================
# DETECTORS
# =====================================================================================

def detect_sink_ids(master: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    rows = []
    sink_ids: list[str] = []
    grp = master[master.rnsr_id.notna()].groupby("rnsr_id")
    for rid, g in grp:
        if len(g) < SINK_MIN_COMPONENTS:
            continue
        labs = g.lab_name.fillna("").tolist()
        toksets = [set(normalize_key(l).split()) for l in labs]
        pair_scores = []
        for i in range(len(toksets)):
            for j in range(i + 1, len(toksets)):
                a, b = toksets[i], toksets[j]
                if not a and not b:
                    continue
                pair_scores.append(jaccard(a, b))
        avg = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
        rows.append({
            "rnsr_id": rid, "n_components": len(g), "n_distinct_labs": g.lab_name.nunique(),
            "avg_pairwise_jaccard": round(avg, 4),
            "sample_labs": "; ".join(sorted(g.lab_name.dropna().unique())[:6]),
            "sum_amount": g.french_component_amount.sum(),
            "is_sink": avg < SINK_AVG_JACCARD_MAX,
        })
        if avg < SINK_AVG_JACCARD_MAX:
            sink_ids.append(rid)
    detector_df = pd.DataFrame(rows).sort_values("rnsr_id").reset_index(drop=True)
    return sorted(sink_ids), detector_df


def detect_token_mismatch(master: pd.DataFrame, active_by_id: pd.DataFrame) -> list[str]:
    out = []
    for _, r in master[master.evidence_grade.isin(["A", "B"])].iterrows():
        rid = r.rnsr_id
        if rid is None or (isinstance(rid, float) and pd.isna(rid)) or rid not in active_by_id.index:
            continue
        arow = active_by_id.loc[rid]
        if isinstance(arow, pd.DataFrame):
            arow = arow.iloc[0]
        j, seq = token_mismatch_score(r.lab_name, arow.get("libelle"))
        if j < TOKEN_MISMATCH_JACCARD_MAX and seq < TOKEN_MISMATCH_SEQ_MAX:
            out.append(r.component_id)
    return sorted(out)


# =====================================================================================
# Documented leads that the never-fuzzy ladder correctly refuses to auto-assign (no token/sigle
# overlap to lab_name -- would require institutional-knowledge inference, out of bounds for this
# pass). Recorded so a future manual/web pass has a concrete starting point, exactly the precedent
# set by evidence_hints.py's own KNOWN_FALSE_POSITIVE_UNLINK docstring for 101063037:0.
# =====================================================================================
EXTRA_NOTES: dict[str, str] = {
    "856455:0": (
        "No RNSR structure named 'World Inequality Lab' or matching 'Paris School of Economics' "
        "exists (searched active.parquet libelle/sigle, 0 hits). A plausible host, Paris-Jourdan "
        "Sciences Economiques (PJSE, UMR 8545, rnsr_id 199812873F, Paris 75014, tutelles incl. "
        "Universite Paris 1 Pantheon-Sorbonne/ENS Paris/EHESS/CNRS/PSL), requires an institutional-"
        "knowledge inference with zero token/sigle overlap to lab_name -- out of bounds for the "
        "never-fuzzy ladder, so NOT auto-assigned; left as a lead for a future manual/web pass."
    ),
    "805256:0": (
        "No active RNSR structure literally named 'Institut de physique du globe de Strasbourg' "
        "exists; IPGS appears to have been folded into EOST (Ecole et Observatoire des Sciences de "
        "la Terre, UAR 830, rnsr_id 199320515J, Strasbourg, tutelles CNRS + Universite de "
        "Strasbourg) at some point in its history, but that identification requires institutional "
        "knowledge with no string-level match to lab_name -- out of bounds for the never-fuzzy "
        "ladder, so NOT auto-assigned; left as a lead for a future manual/web pass."
    ),
}


def classify_confidence(new_rnsr_id, mode, corroborated, hint_source, foreign) -> str:
    if foreign:
        return "needs_review"
    if new_rnsr_id is None:
        return "needs_review"
    if mode and mode.startswith("unique_no_city") and not corroborated:
        return "needs_review"
    if hint_source == "s9a_report_table" and not (mode and mode.startswith("unit_id")):
        return "medium"
    if corroborated:
        return "high"
    return "needs_review"


def process_suspect_row(r, active_by_id, hist_by_id, index: RnsrIndex, sigle_dict, name_nature_dict,
                         sigle_nature_dict, crosswalk_events, fc_by_id, src_evidence, detector_tags):
    cid = r.component_id
    lab_name_raw = r.lab_name
    lab_name = clean_text(lab_name_raw)  # curly-apostrophe-safe copy fed to every matching function

    old_rnsr_id = r.rnsr_id if (r.rnsr_id is not None and not (isinstance(r.rnsr_id, float) and pd.isna(r.rnsr_id))) else None
    old_libelle = None
    if old_rnsr_id and old_rnsr_id in active_by_id.index:
        arow = active_by_id.loc[old_rnsr_id]
        if isinstance(arow, pd.DataFrame):
            arow = arow.iloc[0]
        old_libelle = arow.get("libelle")

    is_phase_c_local = r.match_mode is not None and not (isinstance(r.match_mode, float) and pd.isna(r.match_mode))
    fc_city = fc_by_id.get(cid, {}).get("city") if cid in fc_by_id else None
    hint_city, hint_independent, hint_source = resolve_hint_city(cid, lab_name, is_phase_c_local, r.city, fc_city, src_evidence)
    hint_city = clean_text(hint_city)
    unit_id_text = clean_text(resolve_unit_id_text(cid, src_evidence))

    new_rnsr_id, mode, corroborated = attempt_relink(lab_name, hint_city, unit_id_text, index, active_by_id)

    new_libelle = None
    if new_rnsr_id and new_rnsr_id in active_by_id.index:
        arow = active_by_id.loc[new_rnsr_id]
        if isinstance(arow, pd.DataFrame):
            arow = arow.iloc[0]
        new_libelle = arow.get("libelle")

    region, region_source, cp_out, rnsr_commune, rnsr_cp, region_flags = compute_region(
        new_rnsr_id, hint_city, hint_independent, active_by_id
    )
    flags = list(region_flags)
    foreign = "foreign_postal_code" in flags

    universities_at_start: list[str] = []
    rto: list[str] = []
    other_etab: list[str] = []
    participants: list[str] = []
    tutelle_source = None
    if new_rnsr_id and not foreign:
        start_year = int(r.start_year) if (r.start_year is not None and not (isinstance(r.start_year, float) and pd.isna(r.start_year))) else None
        bucket = tutelles_for_row(new_rnsr_id, start_year, active_by_id, hist_by_id, sigle_dict, name_nature_dict, sigle_nature_dict)
        univ_raw = bucket.get("universities_at_start") or []
        univ_cw, cw_flags, _cw_apps = apply_crosswalk(univ_raw, r.start_date, crosswalk_events)
        universities_at_start = univ_cw
        rto = bucket.get("rto_tutelles") or []
        other_etab = bucket.get("other_etab_tutelles") or []
        participants = bucket.get("participants_nontutelle") or []
        tutelle_source = bucket.get("tutelle_source")
        if bucket.get("conflict_kind"):
            flags.append(bucket["conflict_kind"])
        flags.extend(bucket.get("tutelle_flags") or [])
        flags.extend(cw_flags)

    confidence = classify_confidence(new_rnsr_id, mode, corroborated, hint_source, foreign)

    reason_parts = [f"suspect_via={','.join(detector_tags)}" if detector_tags else "suspect_via=named"]
    reason_parts.append(f"old_rnsr_id={old_rnsr_id!r} old_libelle={old_libelle!r}")
    if new_rnsr_id:
        reason_parts.append(f"relinked via {mode} (hint_city={hint_city!r} source={hint_source!r}) -> {new_rnsr_id} ({new_libelle!r})")
    else:
        reason_parts.append(f"no safe deterministic RNSR candidate (hint_city={hint_city!r} source={hint_source!r}); ladder tried unit_id/embedded-code, whole-name-as-sigle, sigle+city, libelle+city, unique-no-city")
    if region:
        reason_parts.append(f"region={region} via {region_source}")
    if flags:
        reason_parts.append("flags=" + "|".join(sorted(set(flags))))
    if foreign:
        reason_parts.append("RECOMMEND disposition review -> non_french_at_start (foreign performing site; no region forced, no French tutelle credited)")
    if cid in EXTRA_NOTES:
        reason_parts.append(EXTRA_NOTES[cid])
    reason = " | ".join(reason_parts)

    is_conflict = new_rnsr_id is None and region is None

    out = {
        "component_id": cid, "grant_id": r.grant_id, "lab_name": lab_name_raw, "evidence_grade": r.evidence_grade,
        "old_rnsr_id": old_rnsr_id, "old_lab_libelle": old_libelle, "old_region": r.region,
        "new_rnsr_id": new_rnsr_id, "new_match_mode": mode,
        "new_city": hint_city, "new_code_postal": cp_out, "new_region": region,
        "region_source": region_source,
        "hq_address_overridden": "hq_address_overridden" in flags,
        "foreign_postal_code": foreign,
        "tutelle_source": tutelle_source,
        "universities_at_start": joinlist(universities_at_start),
        "rto_tutelles": joinlist(rto),
        "other_etab_tutelles": joinlist(other_etab),
        "participants_nontutelle": joinlist(participants),
        "confidence": confidence,
        "french_component_amount": r.french_component_amount,
        "detector": ",".join(detector_tags) if detector_tags else "named",
        "reason": reason,
    }
    return out, is_conflict


# =====================================================================================
# GATES (self-audit, printed PASS/FAIL like c06_gates_and_outputs.py's own convention)
# =====================================================================================
GATE_RESULTS: dict[str, str] = {}


def gate(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    GATE_RESULTS[name] = status
    aprint(f"GATE [{status}] {name}" + (f" -- {detail}" if detail else ""))


def main() -> None:
    aprint("=== c11_v2_relink ===")
    checkpoint("main() started: loading master, RNSR active/historical, french_components, source component evidence")

    master = pd.read_parquet(MASTER_PARQUET)
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    active_by_id = active.set_index("numero_national_de_structure", drop=False)
    hist_by_id = historical.groupby("numero_national_de_structure")

    fc = pd.read_parquet(FC_PARQUET)
    fc = fc[~fc.component_id.duplicated(keep="first")].set_index("component_id", drop=False)
    fc_by_id = fc.to_dict("index")

    src_evidence = load_source_component_evidence()
    aprint(f"loaded: master={len(master)} rows, active={len(active)}, historical={len(historical)}, "
           f"french_components={len(fc)}, source_component_evidence={len(src_evidence)}")

    index = RnsrIndex(active, historical)
    sigle_dict = build_sigle_name_dict(active, historical)
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)
    crosswalk_events = load_crosswalk_events()
    checkpoint(f"data loaded and index built: {len(master)} master rows, RnsrIndex over {len(active)} active + "
               f"{len(historical)} historical rows, {len(crosswalk_events)} crosswalk events")

    # ---------------- detectors ----------------
    sink_ids, sink_detector_df = detect_sink_ids(master)
    token_mismatch_ids = detect_token_mismatch(master, active_by_id)
    named_ids = list(NAMED_ROW_IDS)

    sink_component_ids = sorted(master[master.rnsr_id.isin(sink_ids)].component_id.tolist())
    aprint(f"sink detector: {len(sink_ids)} rnsr_id(s) qualify -> {sink_ids}, covering {len(sink_component_ids)} components")
    aprint(f"token-mismatch detector (jaccard<{TOKEN_MISMATCH_JACCARD_MAX} AND seq<{TOKEN_MISMATCH_SEQ_MAX}): "
           f"{len(token_mismatch_ids)} components")
    aprint(f"named rows: {len(named_ids)}")

    detector_tags: dict[str, set] = {}
    for cid in sink_component_ids:
        detector_tags.setdefault(cid, set()).add("sink")
    for cid in token_mismatch_ids:
        detector_tags.setdefault(cid, set()).add("token_mismatch")
    for cid in named_ids:
        detector_tags.setdefault(cid, set()).add("named")

    checkpoint(f"detectors run: sink_ids={sink_ids} ({len(sink_component_ids)} components), "
               f"token_mismatch={len(token_mismatch_ids)} components, named={len(named_ids)}; "
               f"union suspect set = {len(detector_tags)} unique components")

    sink_detector_df.to_csv(OUT_DIR / "sink_detector.csv", index=False, encoding="utf-8")

    # ---------------- process every suspect exactly once, in master's own row order ----------------
    override_rows: list[dict] = []
    conflict_rows: list[dict] = []
    master_by_cid = master.set_index("component_id", drop=False)
    for cid in sorted(detector_tags.keys()):
        r = master_by_cid.loc[cid]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        tags = sorted(detector_tags[cid])
        out, is_conflict = process_suspect_row(
            r, active_by_id, hist_by_id, index, sigle_dict, name_nature_dict, sigle_nature_dict,
            crosswalk_events, fc_by_id, src_evidence, tags,
        )
        if is_conflict:
            conflict_rows.append(out)
        else:
            override_rows.append(out)

    overrides_df = pd.DataFrame(override_rows).sort_values("component_id").reset_index(drop=True) if override_rows else pd.DataFrame(
        columns=["component_id", "grant_id", "lab_name", "evidence_grade", "old_rnsr_id", "old_lab_libelle",
                 "old_region", "new_rnsr_id", "new_match_mode", "new_city", "new_code_postal", "new_region",
                 "region_source", "hq_address_overridden", "foreign_postal_code", "tutelle_source",
                 "universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle",
                 "confidence", "french_component_amount", "detector", "reason"])
    conflicts_df = pd.DataFrame(conflict_rows).sort_values("component_id").reset_index(drop=True) if conflict_rows else pd.DataFrame(
        columns=["component_id", "grant_id", "lab_name", "evidence_grade", "old_rnsr_id", "old_lab_libelle",
                 "old_region", "detector", "french_component_amount", "reason"])

    overrides_df.to_csv(OUT_DIR / "v2_relink_overrides.csv", index=False, encoding="utf-8")
    conflicts_cols = ["component_id", "grant_id", "lab_name", "evidence_grade", "old_rnsr_id", "old_lab_libelle",
                       "old_region", "detector", "french_component_amount", "reason"]
    conflicts_df[conflicts_cols].to_csv(OUT_DIR / "v2_relink_conflicts.csv", index=False, encoding="utf-8")

    checkpoint(f"relinked {len(detector_tags)} suspects -> {len(overrides_df)} overrides "
               f"({(overrides_df.confidence == 'high').sum()} high / {(overrides_df.confidence == 'medium').sum()} "
               f"medium / {(overrides_df.confidence == 'needs_review').sum()} needs_review), "
               f"{len(conflicts_df)} unresolved conflicts")

    # ---------------- gates ----------------
    all_suspects = set(detector_tags.keys())
    written = set(overrides_df.component_id) | set(conflicts_df.component_id)
    overlap = set(overrides_df.component_id) & set(conflicts_df.component_id)
    gate("every_suspect_appears_exactly_once", written == all_suspects and not overlap,
         f"suspects={len(all_suspects)} written={len(written)} overlap={len(overlap)}")

    # NOTE: "unique_no_city" (bare, exact string) is the only mode that assigns a candidate on
    # global-uniqueness alone with NO independent cross-check -- it must always be needs_review.
    # "unique_no_city_city_corroborated" cross-validated the candidate's own commune against an
    # independent hint_city and it agreed (a real, if secondary, corroboration), so 'high' is
    # legitimate there; "unique_no_city_contradicted_by_hint_city" never assigns a rnsr_id at all
    # (attempt_relink returns None for it) so it carries no risk this gate needs to police.
    bad_fuzzy = overrides_df[
        (overrides_df.new_match_mode == "unique_no_city") & (overrides_df.confidence != "needs_review")
    ]
    gate("no_unflagged_uniqueness_without_city", len(bad_fuzzy) == 0, f"{len(bad_fuzzy)} violating rows")

    bad_univ = overrides_df[(overrides_df.universities_at_start.fillna("") != "") & (overrides_df.tutelle_source.isna())]
    gate("no_university_without_tutelle_source", len(bad_univ) == 0, f"{len(bad_univ)} violating rows")

    missing_sink = set(sink_component_ids) - written
    gate("all_sink_rows_dispositioned", len(missing_sink) == 0, f"missing={sorted(missing_sink)}")

    missing_named = set(named_ids) - written
    gate("all_named_rows_dispositioned", len(missing_named) == 0, f"missing={sorted(missing_named)}")

    gates_pass = all(v == "PASS" for v in GATE_RESULTS.values())

    # ---------------- sink region migration ----------------
    sink_out = overrides_df[overrides_df.component_id.isin(sink_component_ids)]
    sink_moved = sink_out[sink_out.new_region != "Île-de-France"]
    sink_region_counts = sink_moved.new_region.fillna("NULL").value_counts().to_dict()
    sink_still_idf = int((sink_out.new_region == "Île-de-France").sum())
    sink_conflicts_n = len(conflicts_df[conflicts_df.component_id.isin(sink_component_ids)])

    # ---------------- region migration table (all suspects) ----------------
    all_out = pd.concat([overrides_df.assign(_isconflict=False),
                          conflicts_df.assign(new_region=None, _isconflict=True)], ignore_index=True, sort=False)
    migr = (
        all_out.assign(old_region=all_out.old_region.fillna("NULL"), new_region=all_out.new_region.fillna("NULL"))
        .groupby(["old_region", "new_region"], dropna=False)
        .agg(n=("component_id", "count"), eur=("french_component_amount", "sum"))
        .reset_index()
        .sort_values(["old_region", "new_region"])
    )

    # ---------------- named rows outcomes ----------------
    named_outcomes: dict[str, str] = {}
    for cid in named_ids:
        row = overrides_df[overrides_df.component_id == cid]
        if not row.empty:
            row = row.iloc[0]
            named_outcomes[cid] = (
                f"new_rnsr_id={row.new_rnsr_id} new_region={row.new_region} "
                f"region_source={row.region_source} confidence={row.confidence} mode={row.new_match_mode}"
            )
        else:
            row = conflicts_df[conflicts_df.component_id == cid].iloc[0]
            named_outcomes[cid] = f"UNRESOLVED CONFLICT: {row.reason[:200]}"

    eur_moved = float(overrides_df[overrides_df.old_region != overrides_df.new_region].french_component_amount.sum())

    write_report(
        overrides_df, conflicts_df, sink_detector_df, sink_ids, sink_component_ids, token_mismatch_ids,
        named_ids, named_outcomes, migr, sink_region_counts, sink_still_idf, sink_conflicts_n, eur_moved,
    )

    checkpoint(f"gates: {GATE_RESULTS} -> overall {'ALL_PASS' if gates_pass else 'ISSUES'}; "
               f"sink migration: {sink_still_idf} stayed IdF, moved-out breakdown {sink_region_counts}, "
               f"{sink_conflicts_n} unresolved; eur_moved={eur_moved:,.2f}")

    summary = {
        "suspects": {
            "sink": len(sink_component_ids),
            "token_mismatch": len(token_mismatch_ids),
            "named": len(named_ids),
            "other_sinks": [s for s in sink_ids if s != "202024262P"],
        },
        "relinked": {
            "high": int((overrides_df.confidence == "high").sum()),
            "medium": int((overrides_df.confidence == "medium").sum()),
            "needs_review": int((overrides_df.confidence == "needs_review").sum()),
        },
        "unresolved_conflicts": len(conflicts_df),
        "region_migrations": {"IdF_out": len(sink_moved), **{f"IdF_to_{k}": v for k, v in sink_region_counts.items()}},
        "named_rows": named_outcomes,
        "eur_moved_meur": round(eur_moved / 1_000_000, 3),
        "gates": "ALL_PASS" if gates_pass else "issues",
        "files": [
            str(OUT_DIR / "v2_relink_overrides.csv"),
            str(OUT_DIR / "v2_relink_conflicts.csv"),
            str(OUT_DIR / "sink_detector.csv"),
            str(OUT_DIR / "V2_RELINK_REPORT.md"),
            str(CHECKPOINT),
        ],
        "notes": [
            f"token_mismatch threshold jaccard<{TOKEN_MISMATCH_JACCARD_MAX} AND seq<{TOKEN_MISMATCH_SEQ_MAX} "
            f"(task expected ~148; got {len(token_mismatch_ids)})",
            "948358:0/805256:0/856455:0 resolve through the SAME generic ladder (no hardcoded overrides)",
            "852448:0 (Centre Marc Bloch/Berlin): rnsr_id confirmed correct, region nulled + foreign_postal_code, flagged for non_french_at_start disposition review",
        ],
    }
    (OUT_DIR / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    aprint(json.dumps(summary, ensure_ascii=True, indent=2))
    aprint("c11_v2_relink done.")


def write_report(overrides_df, conflicts_df, sink_detector_df, sink_ids, sink_component_ids,
                  token_mismatch_ids, named_ids, named_outcomes, migr, sink_region_counts,
                  sink_still_idf, sink_conflicts_n, eur_moved) -> None:
    lines = []
    lines.append("# V2 RELINK REPORT (c11_v2_relink.py)\n")
    lines.append("Deterministic, local-only (no web) re-link of the v2-inherited RNSR errors found by "
                  "the S9a hostile data review. Writes ONLY to RUN/staged/v2_relink/; the master and c08 "
                  "are untouched -- the manager integrates via c08.\n")

    lines.append("## Suspect counts by detector\n")
    lines.append(f"- sink (rnsr_id=202024262P, CEA 'Direction des Energies'): **{len(sink_component_ids)}** components")
    lines.append(f"- token_mismatch (jaccard<{TOKEN_MISMATCH_JACCARD_MAX} AND seq<{TOKEN_MISMATCH_SEQ_MAX} vs "
                  f"linked RNSR libelle, grade A/B only): **{len(token_mismatch_ids)}** components")
    lines.append(f"- named (task-required individual outcomes): **{len(named_ids)}** components")
    other_sinks = [s for s in sink_ids if s != "202024262P"]
    lines.append(f"- generic sink detector (>= {SINK_MIN_COMPONENTS} components sharing one rnsr_id, avg "
                  f"pairwise lab_name Jaccard < {SINK_AVG_JACCARD_MAX}): other_sinks = {other_sinks or '[] (none beyond 202024262P)'}\n")

    lines.append("## Re-link outcomes\n")
    n_high = int((overrides_df.confidence == "high").sum())
    n_med = int((overrides_df.confidence == "medium").sum())
    n_nr = int((overrides_df.confidence == "needs_review").sum())
    lines.append(f"- high confidence: **{n_high}**")
    lines.append(f"- medium confidence: **{n_med}**")
    lines.append(f"- needs_review: **{n_nr}**")
    lines.append(f"- unresolved conflicts: **{len(conflicts_df)}**")
    lines.append(f"- total EUR moved to a different region than originally published: **{eur_moved:,.2f}**\n")

    lines.append("## CEA sink (202024262P) disposition\n")
    lines.append(f"- 55 components total; stayed Ile-de-France: **{sink_still_idf}**; unresolved conflicts: "
                  f"**{sink_conflicts_n}**; moved out of Ile-de-France: **{len(sink_component_ids) - sink_still_idf - sink_conflicts_n}**")
    lines.append("- moved-to region breakdown:")
    for region, n in sorted(sink_region_counts.items()):
        lines.append(f"  - {region}: {n}")
    lines.append("")

    lines.append("## Region migrations (old_region -> new_region), all suspects\n")
    lines.append("| old_region | new_region | n | EUR |")
    lines.append("|---|---|---|---|")
    for _, row in migr.iterrows():
        lines.append(f"| {row.old_region} | {row.new_region} | {row.n} | {row.eur:,.2f} |")
    lines.append("")

    lines.append("## The six named rows -- explicit outcomes\n")
    for cid in named_ids:
        lines.append(f"- **{cid}**: {named_outcomes.get(cid, 'MISSING')}")
    lines.append("")

    lines.append("## Gates\n")
    for name, status in GATE_RESULTS.items():
        lines.append(f"- [{status}] {name}")
    lines.append("")

    lines.append("## Files\n")
    lines.append("- v2_relink_overrides.csv -- re-linked suspects (component_id, old/new rnsr_id, new "
                  "city/postal/region + source, re-derived tutelle buckets, confidence, reason)")
    lines.append("- v2_relink_conflicts.csv -- suspects with no safe deterministic outcome at all "
                  "(rnsr_id/region/universities all null)")
    lines.append("- sink_detector.csv -- every rnsr_id shared by >=8 components with its avg pairwise "
                  "lab_name-Jaccard (is_sink flag)")
    lines.append("- RELINK_CHECKPOINT.md -- milestone log\n")

    (OUT_DIR / "V2_RELINK_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
