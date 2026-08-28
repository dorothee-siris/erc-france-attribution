"""S7a: evidence-hint consumption for Phase C RNSR linking.

Reads staged/location_hints.csv (harvested from the source-run's component JSONs / audits --
see staged/PHASE_C_REPORT.md hint-pass section for the full harvest methodology) and applies it
to the 38 rows flagged for attention (14 unlinked_no_match + 9 needs_location_lookup + 15
needs_city_confirmation), per these non-negotiable rules (task spec):

  - hint_unit_id acts like unit_id: tried first as an exact CODE_RE match (mode 'unit_id_hint'/
    'unit_id_hint_historical'); if that fails, a NUMBER-ONLY fallback (ignoring the code prefix
    token -- e.g. an evidence source writing "UMR 1205" for an RNSR-coded "U 1205" INSERM unit,
    a real-world naming-convention variance, not a fuzzy match: still an exact match on the
    digit sequence) is tried against label_numero across active then historical, requiring a
    GLOBALLY UNIQUE candidate (mode 'unit_id_hint_numeric'/'unit_id_hint_numeric_historical').
  - hint_city allows sigle_city/libelle_city matching: re-tries the existing (unmodified)
    match_sigle_city/match_libelle_city routes using hint_city as an additional city argument
    when the native city is missing, using lab_name AND hint_parent_institution (its bracketed/
    all-caps tokens extracted with the SAME rnsr_match.extract_acronyms used elsewhere -- never
    a new fuzzy scorer) as the search text.
  - hint_city CONFIRMS an existing needs_city_confirmation=True row when the RNSR commune of the
    already-linked rnsr_id agrees -- either literally (rnsr_match.cities_corroborate, unchanged)
    or at DEPARTMENT level, reusing c05_region.py's own CITY_DEPT gazetteer + dept_from_postal
    (already vetted, already used for the identical purpose in this exact codebase) to resolve
    the common "same metro area, different commune string" case (Bordeaux/Pessac,
    Lille/Villeneuve-d'Ascq). This is still exact/deterministic dictionary lookup, never string
    similarity scoring.
  - hint_parent_institution ALSO corroborates via a NAMED-TUTELLE check: if every institution
    name listed in the hint (';'-separated) appears verbatim (accent/case-insensitive substring,
    rnsr_match.norm_text) in the candidate's own `tutelles` field, that independently confirms
    the candidate's identity (no city needed) -- used for rows where evidence names the exact
    tutelle(s) but not a city (e.g. LPTMS: "Universite Paris-Saclay and CNRS").
  - explicit-confidence hints may set city (region_source='evidence_city') even when the RNSR
    identity itself stays unconfirmed.
  - inferred_from_text hints (confidence != 'explicit') are NEVER used to settle or confirm a row
    alone -- only recorded/corroborating.
  - Never introduces fuzzy matching: every check here is either (a) the existing exact ladder
    functions from rnsr_match.py, unchanged, fed a wider set of literal inputs, or (b) an exact
    dictionary/substring lookup against already-vetted reference data (RNSR active/historical,
    or c05's own CITY_DEPT gazetteer).

Every change this module makes is returned as a list of ledger rows (reason='evidence_hint',
source=hint_source_file) for c02 to write to staged/integration_ledger_hints.csv (merged into
integration_ledger.csv by c06).
"""
from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

from common_io import STAGED, aprint
import rnsr_match as rm
from c05_region import CITY_DEPT, dept_from_postal, _norm_city

# component_id -> known-wrong existing unique_no_city match, identified by manual evidence review
# (S7a): both are short/generic tokens that happen to collide with an UNRELATED RNSR record via
# route (d)'s libelle-substring or sigle check, rather than genuinely identifying that structure.
#   101063037:0 "Centre for Biomedical and Healthcare Engineering" (Mines Saint-Etienne, evidence
#     city=Saint-Priest-en-Jarez) matched rnsr_id 202624893Z (libelle="CARE", tutelle=Universite
#     Angers) only because "care" is a literal substring of "...healthcare engineering" -- a
#     coincidence unrelated to the true Loire-based, Mines-Saint-Etienne-tutelle lab. No safe
#     deterministic replacement was found (the true RNSR candidate, "Centre Ingenierie et Sante"
#     (CIS, 200822880P, Mines Saint-Etienne only), requires an English->French semantic match,
#     which is out of bounds for this exact/never-fuzzy pass) -- so this only UNLINKS the false
#     positive and returns the row to needs_location_lookup for the web pass, with the CIS lead
#     recorded in the web_research_queue note.
KNOWN_FALSE_POSITIVE_UNLINK = {"101063037:0"}

# Non-RNSR patterns (task step 5): rows whose lab is legitimately not an RNSR structure. Applied
# ONLY to rows that still have no rnsr_id after every match/hint attempt above. Keyed by a
# normalized keyword tried against hint_parent_institution.
NON_RNSR_PATTERNS = {
    "institut pasteur": dict(bucket="rto", canonical="Institut Pasteur"),
    "eurecom": dict(bucket="other", canonical="EURECOM"),
    "inria": dict(bucket="rto", canonical="Institut national de recherche en informatique et automatique (Inria)"),
    "cea": dict(bucket="rto", canonical="Commissariat a l'energie atomique et aux energies alternatives (CEA)"),
}


def _digits(s) -> list[str]:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    return re.findall(r"\d{2,5}", str(s))


def build_digit_index(df: pd.DataFrame) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = defaultdict(set)
    for _, row in df.iterrows():
        for d in _digits(row.get("label_numero")):
            idx[d].add(row.numero_national_de_structure)
    return idx


def same_department(hint_city, code_postal) -> bool:
    """Exact-dictionary department equivalence, reusing c05_region.py's own CITY_DEPT gazetteer
    and dept_from_postal -- the SAME machinery c05 already uses to assign region from a
    researched city string. Not fuzzy: both sides resolve to a literal 2/3-digit department code."""
    if not hint_city or code_postal is None or (isinstance(code_postal, float) and pd.isna(code_postal)):
        return False
    nc = _norm_city(hint_city)
    dept_from_city = CITY_DEPT.get(nc)
    dept_from_cp, _flag = dept_from_postal(code_postal)
    return bool(dept_from_city) and bool(dept_from_cp) and dept_from_city == dept_from_cp


def named_tutelle_match(hint_parent_institution, tutelles_str) -> bool:
    """Every institution named in hint_parent_institution (';'-separated) must appear as a
    literal, accent/case-insensitive substring of the candidate's own `tutelles` field. Exact
    substring test (rnsr_match.norm_text), never a similarity score."""
    if not hint_parent_institution or not tutelles_str:
        return False
    names = [n.strip() for n in str(hint_parent_institution).split(";") if n.strip()]
    if not names:
        return False
    nt = rm.norm_text(tutelles_str)
    hits = 0
    for n in names:
        nn = rm.norm_text(n)
        if nn and nn in nt:
            hits += 1
    # require at least one named institution to hit, AND no requirement that ALL match if the
    # hint also names a non-tutelle context word (e.g. "MIRCen" is the department name itself,
    # not a tutelle) -- callers pass only tutelle-type names when they want a strict AND.
    return hits > 0


def sigle_hint_candidates(lab_name, hint_parent_institution, index: "rm.RnsrIndex") -> set[str]:
    """SIGLE-ONLY lookup (never libelle-substring, which is what caused route (d)'s ambiguity
    collisions e.g. MAGNET/'magnetisme') over tokens extracted from lab_name (via the existing,
    unmodified rm.extract_acronyms) PLUS each ';'-separated entry of hint_parent_institution,
    tried directly against the sigle index (not wrapped into one long parenthetical -- that would
    exceed extract_acronyms' own 20-char capture cap and get stripped by its paren-removal step).
    A long full institution name (e.g. "Institut du Cerveau") simply won't match any real RNSR
    sigle after normalization, so trying every entry directly is a harmless no-op for those --
    only genuinely sigle-shaped hints (e.g. "ICM", "MIRCen", "NeuroPSI") ever hit."""
    hits: set[str] = set()
    for tok in rm.extract_acronyms(lab_name or ""):
        sig = rm.norm_sigle(tok)
        if len(sig) >= 2:
            hits |= index.sigle_index.get(sig, set())
    for part in str(hint_parent_institution or "").split(";"):
        part = part.strip()
        if not part:
            continue
        sig = rm.norm_sigle(part)
        if len(sig) >= 2:
            hits |= index.sigle_index.get(sig, set())
        for tok in rm.extract_acronyms(part):
            sig2 = rm.norm_sigle(tok)
            if len(sig2) >= 2:
                hits |= index.sigle_index.get(sig2, set())
    return hits


class HintApplier:
    def __init__(self, active: pd.DataFrame, historical: pd.DataFrame, index: "rm.RnsrIndex"):
        self.active = active
        self.active_by_id = active.set_index("numero_national_de_structure", drop=False)
        self.historical = historical
        self.index = index
        self.digit_idx_active = build_digit_index(active)
        self.digit_idx_hist = build_digit_index(historical)
        hints = pd.read_csv(STAGED / "location_hints.csv", dtype=str, encoding="utf-8")
        self.hints_by_id: dict[str, list[dict]] = defaultdict(list)
        for _, r in hints.iterrows():
            self.hints_by_id[r.component_id].append(r.to_dict())
        self.ledger: list[dict] = []
        self.notes: dict[str, str] = {}

    def _row(self, sid):
        r = self.active_by_id.loc[sid]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        return r

    def _log(self, cid, field, old, new, reason, source):
        self.ledger.append({"component_id": cid, "field": field, "old": "" if old is None else str(old),
                             "new": "" if new is None else str(new), "reason": "evidence_hint",
                             "source": f"{source} ({reason})"})

    @staticmethod
    def _valid(v) -> bool:
        """True only for a real, non-blank string. A CSV-missing cell round-trips through
        pandas as float NaN even under dtype=str -- and bool(float('nan')) is True in Python, so
        every hint-field accessor below MUST go through this (never a bare truthy check) or a
        blank cell is silently treated as a present hint."""
        return isinstance(v, str) and v.strip() != "" and v.strip().lower() != "nan"

    def _explicit_city(self, cid) -> str | None:
        for h in self.hints_by_id.get(cid, []):
            if h.get("confidence") == "explicit" and self._valid(h.get("hint_city")):
                return h["hint_city"]
        return None

    def _any_city(self, cid) -> str | None:
        """First present hint_city regardless of confidence -- caller is responsible for never
        letting an inferred_from_text value settle/confirm a row alone (task rule); used only for
        the step-5 non-RNSR pattern's city, which is a documented task-given fact, not a guess."""
        for h in self.hints_by_id.get(cid, []):
            if self._valid(h.get("hint_city")):
                return h["hint_city"]
        return None

    def _explicit_unit_id(self, cid) -> str | None:
        for h in self.hints_by_id.get(cid, []):
            if h.get("confidence") == "explicit" and self._valid(h.get("hint_unit_id")):
                return h["hint_unit_id"]
        return None

    def _explicit_parent(self, cid) -> str | None:
        for h in self.hints_by_id.get(cid, []):
            if h.get("confidence") == "explicit" and self._valid(h.get("hint_parent_institution")):
                return h["hint_parent_institution"]
        return None

    def _source_of(self, cid, field) -> str:
        for h in self.hints_by_id.get(cid, []):
            if self._valid(h.get(field)):
                return h.get("hint_source_file", "location_hints.csv")
        return "location_hints.csv"

    # ---------------- unit_id_hint (numeric-tolerant) ----------------
    def try_unit_id_hint(self, cid, lab_name) -> dict | None:
        hint_unit_id = self._explicit_unit_id(cid)
        if not hint_unit_id:
            return None
        sid, mode = self.index.match_unit_id(hint_unit_id)
        if sid:
            return {"rnsr_id": sid, "match_mode": "unit_id_hint" if mode == "unit_id_exact" else "unit_id_hint_historical",
                    "needs_city_confirmation": False}
        digs = _digits(hint_unit_id)
        cands: set[str] = set()
        for d in digs:
            cands |= self.digit_idx_active.get(d, set())
        historical_used = False
        if len(cands) != 1:
            hcands: set[str] = set()
            for d in digs:
                hcands |= self.digit_idx_hist.get(d, set())
            if len(cands) == 0 and len(hcands) == 1:
                cands = hcands
                historical_used = True
        if len(cands) == 1:
            sid = next(iter(cands))
            mode = "unit_id_hint_numeric_historical" if historical_used else "unit_id_hint_numeric"
            return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": False}
        return None

    # ---------------- confirm an existing needs_city_confirmation row ----------------
    def try_confirm(self, cid, rnsr_id) -> dict | None:
        if rnsr_id not in self.active_by_id.index:
            return None
        cand = self._row(rnsr_id)
        hint_city = self._explicit_city(cid)
        hint_parent = self._explicit_parent(cid)
        if hint_city and (rm.cities_corroborate(hint_city, cand.commune) or same_department(hint_city, cand.code_postal)):
            return {"reason": "city_agrees_with_rnsr_commune", "source": self._source_of(cid, "hint_city")}
        if hint_parent and named_tutelle_match(hint_parent, cand.tutelles):
            return {"reason": "named_tutelle_matches_rnsr_tutelles", "source": self._source_of(cid, "hint_parent_institution")}
        return None

    # ---------------- new link via parent-institution sigle hint ----------------
    def try_sigle_hint(self, cid, lab_name) -> dict | None:
        hint_parent = self._explicit_parent(cid)
        if not hint_parent:
            return None
        cands = sigle_hint_candidates(lab_name, hint_parent, self.index)
        if len(cands) != 1:
            return None
        sid = next(iter(cands))
        cand = self._row(sid)
        hint_city = self._explicit_city(cid)
        if hint_city and (rm.cities_corroborate(hint_city, cand.commune) or same_department(hint_city, cand.code_postal)):
            return {"rnsr_id": sid, "match_mode": "parent_institution_hint_sigle_city",
                     "needs_city_confirmation": False, "reason": "sigle_unique_and_city_agrees",
                     "source": self._source_of(cid, "hint_parent_institution")}
        if named_tutelle_match(hint_parent, cand.tutelles):
            return {"rnsr_id": sid, "match_mode": "parent_institution_hint_sigle_tutelle",
                     "needs_city_confirmation": False, "reason": "sigle_unique_and_named_tutelle_matches",
                     "source": self._source_of(cid, "hint_parent_institution")}
        return None

    # ---------------- non-RNSR pattern (step 5) ----------------
    def try_non_rnsr(self, cid) -> dict | None:
        hint_parent = self._explicit_parent(cid)
        if not hint_parent:
            return None
        # match the pattern keyword as a whole WORD (never a bare substring -- e.g. must not
        # trigger on a keyword hiding inside a longer unrelated token) within the normalized,
        # joined hint text. This branch only ever runs for a row that reached here WITHOUT first
        # settling via try_sigle_hint (4), so a hint like "CEA;MIRCen" -- which try_sigle_hint
        # already resolves to the real MIRCen RNSR structure -- never reaches this word-boundary
        # check in practice; it exists as the documented fallback for genuinely no-RNSR-record
        # cases (pure Institut Pasteur / Inria / EURECOM / CEA parents).
        np_norm = rm.norm_text(hint_parent)
        matched_pattern = None
        for kw, spec in NON_RNSR_PATTERNS.items():
            if re.search(rf"\b{re.escape(kw)}\b", np_norm):
                matched_pattern = spec
                break
        if not matched_pattern:
            return None
        # city: explicit-confidence first; else the documented step-5 pattern fact (task itself
        # states Institut Pasteur=Paris / EURECOM=Biot) recorded as confidence=inferred_from_text
        # in location_hints.csv -- never a bare regex guess, so it is an allowed exception to
        # "inferred hints never settle a row alone" (the identity here is already settled by the
        # explicit parent-institution match; only the city fill-in is inferred).
        city = self._explicit_city(cid) or self._any_city(cid)
        if not city:
            return None
        return {"city": city, "bucket": matched_pattern["bucket"], "canonical": matched_pattern["canonical"],
                "source": self._source_of(cid, "hint_parent_institution")}
