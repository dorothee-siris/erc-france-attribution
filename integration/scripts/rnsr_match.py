"""RNSR structure-identification helpers shared by c02 (link) and c03/c04 (tutelle lookup).

Match ladder (strongest first, per task spec -- NEVER fuzzy name-match alone):
  (a) unit_id exact  -- normalize codes like 'UMR 7373'/'UMR7373'/'UMR CNRS 7641' and match
      against RNSR's label_numero, tried against the ACTIVE snapshot first, then HISTORICAL
      (older/renumbered/dissolved units) as a fallback, each independently required to resolve
      to exactly ONE structure id.
  (b) exact sigle match (RNSR's own `sigle` field, not the tutelle sigles) + city corroboration
  (c) exact/normalized libelle match (full-phrase containment, not token-overlap fuzzy scoring)
      + city corroboration
  (d) unique unambiguous exact name/sigle match WITHOUT city -- only accepted when it resolves
      to exactly 1 candidate in the whole of RNSR active
  (e) no match -> None

This module is adapted from V2\\scripts\\rnsr_link.py's normalization helpers (read-only,
checksummed) but REPLACES its Jaccard-threshold fuzzy scorer with strict exact/substring tests,
per this task's stricter non-negotiable-semantics boundary (never fuzzy-match alone).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import pandas as pd

CODE_RE = re.compile(
    r'\b(UMR[-_]?S|UMR|UMI|URA|UPR|UMS|UAR|USR|UOR|EPCP|GDR|FRE|ERL|EA|UR|U)'
    r'[\s\-_/]*'
    r'(?:[A-Za-z][A-Za-z\-]{1,15}[\s\-_]+)?'
    r'(\d{2,5})\b',
    re.I,
)


def extract_codes(s) -> set[str]:
    if not s or (isinstance(s, float) and pd.isna(s)):
        return set()
    out = set()
    for m in CODE_RE.finditer(str(s)):
        prefix = m.group(1).upper().replace("-", "").replace("_", "")
        out.add(f"{prefix}{m.group(2)}")
    return out


def norm_text(value) -> str:
    """Accent-strip, lowercase, punctuation-collapse-to-space normalizer."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"\bCEDEX\b.*$", "", ascii_value, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9 ]", " ", ascii_value.lower())).strip()


def cities_corroborate(city_a, city_b) -> bool:
    na, nb = norm_text(city_a), norm_text(city_b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def extract_acronyms(lab_name) -> list[str]:
    """Parenthesised acronym(s) plus any standalone all-caps-ish token of length>=2."""
    if not lab_name or (isinstance(lab_name, float) and pd.isna(lab_name)):
        return []
    s = str(lab_name)
    out = []
    for m in re.finditer(r"\(([^()]{2,20})\)", s):
        out.append(m.group(1))
    for tok in re.findall(r"\b[A-Z][A-Za-z0-9]{1,12}\b", re.sub(r"\([^()]*\)", "", s)):
        if sum(1 for c in tok if c.isupper()) >= 2 or tok.isupper():
            out.append(tok)
    return out


def norm_sigle(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower()) if value else ""


class RnsrIndex:
    """Built once from active.parquet (+ historical.parquet for the unit_id fallback rung)."""

    def __init__(self, active: pd.DataFrame, historical: pd.DataFrame):
        self.active = active
        self.by_id = active.set_index("numero_national_de_structure", drop=False)

        self.code_index: dict[str, set[str]] = defaultdict(set)
        for _, row in active.iterrows():
            for c in extract_codes(row.get("label_numero")):
                self.code_index[c].add(row.numero_national_de_structure)

        self.hist_code_index: dict[str, set[str]] = defaultdict(set)
        for _, row in historical.iterrows():
            for c in extract_codes(row.get("label_numero")):
                self.hist_code_index[c].add(row.numero_national_de_structure)

        self.sigle_index: dict[str, set[str]] = defaultdict(set)
        for _, row in active.iterrows():
            sig = norm_sigle(row.get("sigle"))
            if len(sig) >= 2:
                self.sigle_index[sig].add(row.numero_national_de_structure)

        # normalized libelle -> set(ids); also keep the raw list for substring containment tests
        self.libelle_rows: list[tuple[str, str, str]] = []  # (norm_libelle, commune, id)
        for _, row in active.iterrows():
            self.libelle_rows.append((norm_text(row.get("libelle")), row.get("commune"), row.numero_national_de_structure))

    def match_unit_id(self, unit_id) -> tuple[str | None, str | None]:
        codes = extract_codes(unit_id)
        if not codes:
            return None, None
        ids = set()
        for c in codes:
            ids |= self.code_index.get(c, set())
        if len(ids) == 1:
            return next(iter(ids)), "unit_id_exact"
        if len(ids) > 1:
            return None, "unit_id_ambiguous"
        # fallback: historical label_numero (older/renumbered/dissolved codes)
        hids = set()
        for c in codes:
            hids |= self.hist_code_index.get(c, set())
        if len(hids) == 1:
            return next(iter(hids)), "unit_id_historical"
        if len(hids) > 1:
            return None, "unit_id_ambiguous_historical"
        return None, None

    def match_sigle_city(self, lab_name, city) -> tuple[str | None, str | None]:
        for tok in extract_acronyms(lab_name):
            sig = norm_sigle(tok)
            if len(sig) < 2:
                continue
            ids = self.sigle_index.get(sig, set())
            if len(ids) == 1:
                sid = next(iter(ids))
                commune = self.by_id.loc[sid, "commune"]
                if cities_corroborate(city, commune):
                    return sid, "sigle_city"
        return None, None

    def match_libelle_city(self, lab_name, city) -> tuple[str | None, str | None]:
        nl = norm_text(lab_name)
        if not nl:
            return None, None
        candidates = []
        for norm_lib, commune, sid in self.libelle_rows:
            if not norm_lib:
                continue
            if norm_lib in nl or nl in norm_lib:
                if cities_corroborate(city, commune):
                    candidates.append(sid)
        uniq = set(candidates)
        if len(uniq) == 1:
            return next(iter(uniq)), "libelle_city"
        return None, None

    def match_unique_no_city(self, lab_name) -> tuple[str | None, str | None]:
        """Route (d): exactly one candidate in the whole of RNSR active, via sigle or libelle,
        with NO city corroboration available/required (uniqueness is the safety net)."""
        sig_hits = set()
        for tok in extract_acronyms(lab_name):
            sig = norm_sigle(tok)
            if len(sig) >= 2:
                sig_hits |= self.sigle_index.get(sig, set())
        nl = norm_text(lab_name)
        lib_hits = set()
        if nl:
            for norm_lib, _commune, sid in self.libelle_rows:
                if norm_lib and (norm_lib in nl or nl in norm_lib):
                    lib_hits.add(sid)
        combined = sig_hits | lib_hits
        if len(combined) == 1:
            return next(iter(combined)), "unique_no_city"
        return None, None

    def link(self, unit_id, lab_name, city) -> dict:
        sid, mode = self.match_unit_id(unit_id)
        if sid:
            return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": False}
        if mode in ("unit_id_ambiguous", "unit_id_ambiguous_historical"):
            return {"rnsr_id": None, "match_mode": mode, "needs_city_confirmation": False}

        sid, mode = self.match_sigle_city(lab_name, city)
        if sid:
            return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": False}

        sid, mode = self.match_libelle_city(lab_name, city)
        if sid:
            return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": False}

        sid, mode = self.match_unique_no_city(lab_name)
        if sid:
            return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": True}

        return {"rnsr_id": None, "match_mode": "no_match", "needs_city_confirmation": False}
