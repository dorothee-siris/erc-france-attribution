"""Robust, verified parsing of RNSR's comma-joined parallel tutelle lists.

THE LANDMINE: RNSR's `tutelles` (institution full names) field is comma-joined, but some
institution names themselves contain a comma (e.g. INRAE's and Institut Agro's full legal
names: "...pour l'agriculture, l'alimentation et l'environnement"), so a naive
`tutelles.split(',')` silently misaligns with the other parallel comma-joined columns
(sigles, codes) whenever such a name is present. Verified empirically (2026-08-27) against
the full active.parquet (4,767 rows) and historical.parquet (88,878 rows) snapshots:

THE BUCKETING BUG (S7f, 2026-08-27): historical.parquet's nature-classification column
(code_de_type_de_tutelle -- UNIV/EPST/EPIC/...) is frequently SHORTER than the reliable
type-flag column (code_de_nature_de_tutelle -- 6/7) that fixes N for the row, whenever one of
the N tutelles lacks a recorded nature code (observed for ~0.3% of structure x year groups,
concentrated on non-standard participants like blood banks, ministries, or hospitals sitting
alongside ordinary CNRS/INSERM/university tutelles). The ORIGINAL code detected this
`historical_nature_code_misaligned` case correctly but then gave up entirely -- every tutelle
in the row fell back to bucket "unknown_unaligned", which c03's bucket_lists() then dumped into
other_etab_tutelles regardless of whether it was actually a university or an RTO (verified
empirically against MechanoFate/SYNC_DEV/EPITOR/ConvergeAnt et al., 2026-08-27). NOTE: this is
NOT a cross-year swapped-convention problem -- the code_de_nature_de_tutelle value set is {6,7}
and the code_de_type_de_tutelle value set is {UNIV,EPST,EPIC,AUTRE,...} consistently across
every year 1990-2017 (checked directly against the full historical.parquet); the swap vs active
is a fixed, row-independent relabeling, not something that flips per row/year. The bug is pure
list-length misalignment, not vocabulary ambiguity.

THE FIX: when a historical row's nature-code list doesn't align to N, resolve each unaligned
tutelle's nature via cross-reference tiers built from every OTHER row (active + historical)
where alignment already holds cleanly, in order:
  1. NAME lookup (build_name_nature_dict): majority-vote nature code for this exact tutelle
     name across the whole corpus. Verified empirically (2026-08-27): cross-checking every
     length-ALIGNED historical row's own per-position nature code against this dictionary's
     majority vote agrees 113872/113917 = 99.96% of the time; the ~0.04% disagreements are real
     historical facts (e.g. an IUFM that later merged into its university, still tagged IUFM in
     an old snapshot year), not encoding noise -- so the dictionary is safe to trust.
  2. SIGLE lookup (build_sigle_nature_dict): same majority-vote construction keyed by sigle,
     for tutelle entries whose name itself could not be recovered but whose sigle was.
  3. Keyword fallback: name starts with "universit" (accent/case-insensitive) -> university.
     Flagged tutelle_class_keyword_fallback so it is auditable and never silent.
  4. UAI lookup was evaluated and REJECTED as a tier: uai_des_tutelles suffers the exact same
     drop-entries-without-a-UAI problem documented below for active.parquet, so once a row's
     tutelle list has already lost positional alignment, the UAI list's own positions can no
     longer be trusted to correspond to a specific institution either (verified empirically:
     manually cross-checking the "recovered" UAI for the École nationale de formation
     agronomique de Toulouse Auzeville in the ANGI/200311846T row actually resolved to
     Université Toulouse III - Paul Sabatier's UAI instead, confirming the same silent-drop
     shift as active's uai_des_tutelles). Any tutelle that still resolves to nothing after tiers
     1-3 keeps nature_code=None and buckets to other_etab (the pre-existing conservative
     default), unflagged beyond historical_nature_code_misaligned.

ACTIVE format (one row per structure, current snapshot):
  - code_de_type_de_tutelle  = TUTE|PART            (comma-safe: 0/4767 count mismatches vs itself)
  - code_de_nature_de_tutelle = UNIV|EPST|EPIC|AUT_ETAB|UNIV_ETR|... (comma-safe; count ALWAYS
    equals code_de_type_de_tutelle's count -> this pair is the reliable ground-truth N)
  - sigles_des_tutelles: aligned to N in 4766/4767 rows (99.98%)
  - tutelles (full names): aligned to N in only 4322/4767 rows (90.7%) -- embedded commas
  - uai_des_tutelles / siret_des_tutelles: UNRELIABLE for alignment -- they DROP entries that
    lack a UAI/SIRET (foreign or private tutelles) rather than leaving a positional blank, so
    their comma-count is frequently LESS than N even when there is no embedded-comma problem.
    Never use them to establish list length (contradicts the task memo's suggestion; verified
    empirically that they are not in fact comma-safe-and-complete).

HISTORICAL format (one row per structure x annee x tutelle-list, 1990-2017; NOTE: nature and
type are SWAPPED vs active, verified empirically):
  - code_de_nature_de_tutelle = '6'|'7' (6=Etablissement tutelle / TUTE, 7=Etablissement
    participant / PART) -- this is actually the TYPE flag despite the "nature" name. Always
    present -> reliable ground-truth N.
  - code_de_type_de_tutelle = UNIV|EPST|EPIC|UT|INSA|ENS|COMUE|... -- this is actually the
    NATURE-like classification despite the "type" name. Aligned to N in ~90.4% of rows
    (drops entries whose nature wasn't recorded); NOT always aligned -- verify per row.
  - tutelles (full names): aligned to N in 85,871/88,878 rows (96.6%) -- the best of the three
    positional columns for historical, used directly when aligned.
  - sigles_des_tutelles: far less reliable here (only ~61% of non-null rows align) -- not used.

Universities-of-technology confirmed coded UNIV in the active vocabulary (e.g. "Universite de
Technologie de Compiegne/Troyes/Belfort-Montbeliard/Tarbes" all carry code_de_nature_de_tutelle
== 'UNIV'), so the historical-format code 'UT' is mapped to the university bucket too, for
consistency with the active-format ground truth. Everything else non-UNIV/non-EPST/non-EPIC in
historical (ENS, INSA, IEP, COMUE, IUFM, PRES, ECENTRALE, ENSI, ENI, ENSCHIMIE, ENS Mines,
IPINP, FONDATION, PRIVE, EPA, AUTRE, INGAUTRE, EFE) is conservatively bucketed as other_etab
(grandes ecoles / hospitals / foundations are not universities) -- documented in the report as
a limitation, never silently upgraded to a university claim.

Design: when the *names* list doesn't align to N (embedded comma), we recover each name via a
GLOBAL sigle -> canonical-name lookup built once from every row (across both active and
historical) where alignment already succeeded cleanly. If the sigle at that position is not in
the dictionary either, the name is left unrecoverable and the row is flagged for a conflict.
"""
from __future__ import annotations

import unicodedata
from collections import Counter

import pandas as pd

ACTIVE_UNIV_CODES = {"UNIV"}  # UNIV_ETR excluded on purpose: foreign, never a French-credit tutelle
ACTIVE_RTO_CODES = {"EPST", "EPIC"}
# everything else TUTE (AUT_ETAB, EPA, FONDATION, PRIVE, SITE, AUT_OP_FR, AUT_OP_ETR, OP_PUB_ETR,
# SOC_PR_ETR, MEDIC, UNIV_ETR) -> other_etab

HIST_UNIV_CODES = {"UNIV", "UT"}  # UT = Universite de technologie, confirmed UNIV-equivalent above
HIST_RTO_CODES = {"EPST", "EPIC"}
# everything else (ENS, INSA, COMUE, IEP, IUFM, PRES, ECENTRALE, ENSI, ENI, ENSCHIMIE,
# "ENS Mines", IPINP, FONDATION, PRIVE, EPA, AUTRE, INGAUTRE, EFE) -> other_etab


def _split(s) -> list[str]:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    return [x.strip() for x in str(s).split(",")]


def bucket_active(nature_code: str) -> str:
    if nature_code in ACTIVE_UNIV_CODES:
        return "university"
    if nature_code in ACTIVE_RTO_CODES:
        return "rto"
    return "other_etab"


def bucket_historical(nature_code: str) -> str:
    if nature_code in HIST_UNIV_CODES:
        return "university"
    if nature_code in HIST_RTO_CODES:
        return "rto"
    return "other_etab"


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _looks_like_university(name: str) -> bool:
    """Final-tier keyword fallback (documented, flagged tutelle_class_keyword_fallback when
    used) -- accent/case-insensitive 'universit' prefix match, e.g. matches 'Universite de X',
    'UNIVERSITE DE Y', 'Universite et assimile'. Never matches e.g. 'Union...' or institution
    names that merely mention a university mid-string (prefix-only, not substring)."""
    return _strip_accents(name).strip().lower().startswith("universit")


def build_name_nature_dict(active: pd.DataFrame, historical: pd.DataFrame) -> dict[str, str]:
    """Global tutelle NAME -> most-common nature/type classification code (UNIV/EPST/EPIC/...),
    harvested ONLY from rows where the row's own type-count and nature-count columns already
    agree in length with the names list -- i.e. exclusively from associations the row itself
    already verifies, never from a guess. See module docstring ("THE FIX", tier 1) for the
    99.96% empirical cross-check that justifies trusting this dictionary as a cross-reference
    for rows where the row's own nature-code list does NOT align."""
    counter: dict[str, Counter] = {}

    def _absorb(df: pd.DataFrame, type_col: str, nature_col: str):
        for tut, typ, nat in zip(df["tutelles"].fillna(""), df[type_col].fillna(""), df[nature_col].fillna("")):
            names = _split(tut)
            types = _split(typ)
            natures = _split(nat)
            if not names or len(names) != len(types) or len(names) != len(natures):
                continue
            for n, c in zip(names, natures):
                if not n or not c:
                    continue
                counter.setdefault(n, Counter())[c] += 1

    _absorb(active, "code_de_type_de_tutelle", "code_de_nature_de_tutelle")
    _absorb(historical, "code_de_nature_de_tutelle", "code_de_type_de_tutelle")  # swapped semantics
    return {n: c.most_common(1)[0][0] for n, c in counter.items()}


def build_sigle_nature_dict(active: pd.DataFrame, historical: pd.DataFrame) -> dict[str, str]:
    """Global tutelle SIGLE -> most-common nature/type classification code, same
    trust-only-fully-aligned-rows construction as build_name_nature_dict (tier 2 fallback, for
    tutelle entries whose NAME could not be recovered but whose SIGLE was)."""
    counter: dict[str, Counter] = {}

    def _absorb(df: pd.DataFrame, type_col: str, nature_col: str):
        for sig, typ, nat in zip(df["sigles_des_tutelles"].fillna(""), df[type_col].fillna(""), df[nature_col].fillna("")):
            sigles = _split(sig)
            types = _split(typ)
            natures = _split(nat)
            if not sigles or len(sigles) != len(types) or len(sigles) != len(natures):
                continue
            for s, c in zip(sigles, natures):
                if not s or not c:
                    continue
                counter.setdefault(s, Counter())[c] += 1

    _absorb(active, "code_de_type_de_tutelle", "code_de_nature_de_tutelle")
    _absorb(historical, "code_de_nature_de_tutelle", "code_de_type_de_tutelle")  # swapped semantics
    return {s: c.most_common(1)[0][0] for s, c in counter.items()}


def build_sigle_name_dict(active: pd.DataFrame, historical: pd.DataFrame) -> dict[str, str]:
    """Global sigle -> most-common canonical full name.

    Two harvesting passes:
    1. Multi-tutelle rows where the raw names list already aligns 1:1 with the raw sigles list.
    2. SINGLETON rows (exactly one tutelle, per the type-code ground truth) -- here the entire
       raw `tutelles` string IS the one name, verbatim, commas and all, so this is the only way
       to ever recover institutions whose OFFICIAL full name itself contains a comma (e.g. INRAE:
       "Institut national de recherche pour l'agriculture, l'alimentation et l'environnement", or
       Institut Agro's equivalent) -- such a name can never appear in an "aligned" multi-tutelle
       row by construction, so pass 1 alone can never learn it."""
    counter: dict[str, Counter] = {}

    def _absorb_aligned(df: pd.DataFrame):
        for tut, sig in zip(df["tutelles"].fillna(""), df["sigles_des_tutelles"].fillna("")):
            names = _split(tut)
            sigles = _split(sig)
            if not names or len(names) != len(sigles):
                continue
            for n, s in zip(names, sigles):
                if not s or not n:
                    continue
                counter.setdefault(s, Counter())[n] += 1

    def _absorb_singletons(df: pd.DataFrame, type_col: str):
        n_type = df[type_col].fillna("").apply(lambda s: len(_split(s)) if s else 0)
        singles = df[n_type == 1]
        for tut, sig in zip(singles["tutelles"].fillna(""), singles["sigles_des_tutelles"].fillna("")):
            sigles = _split(sig)
            if len(sigles) != 1 or not sigles[0] or not tut:
                continue
            counter.setdefault(sigles[0], Counter())[str(tut).strip()] += 1

    _absorb_aligned(active)
    _absorb_aligned(historical)
    _absorb_singletons(active, "code_de_type_de_tutelle")
    _absorb_singletons(historical, "code_de_nature_de_tutelle")  # swapped semantics, see module docstring
    return {s: c.most_common(1)[0][0] for s, c in counter.items()}


def parse_active_row(row: pd.Series, sigle_name_dict: dict[str, str]) -> dict:
    """Parse one active.parquet row into aligned per-tutelle records + an alignment report."""
    type_codes = _split(row.get("code_de_type_de_tutelle"))   # TUTE|PART
    nature_codes = _split(row.get("code_de_nature_de_tutelle"))  # UNIV|EPST|...
    n = len(type_codes)
    flags: list[str] = []
    if len(nature_codes) != n:
        flags.append("active_type_nature_count_mismatch")
        return {"aligned": False, "flags": flags, "tutelles": []}

    names = _split(row.get("tutelles"))
    sigles = _split(row.get("sigles_des_tutelles"))
    if len(names) == n:
        name_source = "direct"
    elif len(sigles) == n:
        names = [sigle_name_dict.get(s, f"UNKNOWN_NAME[{s}]") for s in sigles]
        name_source = "sigle_lookup"
        flags.append("tutelle_name_via_sigle_lookup")
        if any(nm.startswith("UNKNOWN_NAME[") for nm in names):
            flags.append("tutelle_name_unrecoverable")
    else:
        flags.append("tutelle_name_unrecoverable")
        names = [f"UNKNOWN_NAME[pos{i}]" for i in range(n)]
        name_source = "unresolved"

    recs = []
    for i in range(n):
        recs.append({
            "name": names[i] if i < len(names) else None,
            "sigle": sigles[i] if len(sigles) == n else None,
            "type_code": type_codes[i],   # TUTE / PART
            "nature_code": nature_codes[i],  # UNIV / EPST / ...
            "bucket": bucket_active(nature_codes[i]),
        })
    return {"aligned": True, "flags": flags, "name_source": name_source, "tutelles": recs}


def parse_historical_row(row: pd.Series, sigle_name_dict: dict[str, str],
                          name_nature_dict: dict[str, str] | None = None,
                          sigle_nature_dict: dict[str, str] | None = None) -> dict:
    """Parse one historical.parquet row (already filtered to one structure x one annee) into
    aligned per-tutelle records + an alignment report. Column semantics are SWAPPED vs active.

    S7f fix (2026-08-27): when the row's own nature-code list does not align to N (the
    `historical_nature_code_misaligned` case), each affected tutelle's nature is resolved via
    name_nature_dict / sigle_nature_dict / keyword fallback instead of being dumped unclassified
    into other_etab -- see module docstring "THE BUCKETING BUG" / "THE FIX" for the diagnosis and
    the empirical justification for trusting these cross-reference dictionaries."""
    type_flag_codes = _split(row.get("code_de_nature_de_tutelle"))  # '6'/'7' -> TUTE/PART (real type)
    n = len(type_flag_codes)
    flags: list[str] = []
    if n == 0:
        flags.append("historical_no_tutelles_recorded")
        return {"aligned": False, "flags": flags, "tutelles": []}

    nature_codes = _split(row.get("code_de_type_de_tutelle"))  # UNIV/EPST/... (real nature)
    nature_aligned = len(nature_codes) == n
    if not nature_aligned:
        flags.append("historical_nature_code_misaligned")

    names = _split(row.get("tutelles"))
    if len(names) == n:
        name_source = "direct"
    else:
        sigles = _split(row.get("sigles_des_tutelles"))
        if len(sigles) == n and all(s in sigle_name_dict for s in sigles if s):
            names = [sigle_name_dict.get(s, f"UNKNOWN_NAME[{s}]") for s in sigles]
            name_source = "sigle_lookup"
            flags.append("tutelle_name_via_sigle_lookup")
        else:
            flags.append("tutelle_name_unrecoverable")
            names = [f"UNKNOWN_NAME[pos{i}]" for i in range(n)]
            name_source = "unresolved"

    # Raw sigle list, only usable positionally when it itself aligns to N (tier-2 fallback key).
    raw_sigles = _split(row.get("sigles_des_tutelles"))
    sigles_aligned = len(raw_sigles) == n

    recs = []
    used_name_lookup = used_sigle_lookup = used_keyword_fallback = False
    for i in range(n):
        type_code = "TUTE" if type_flag_codes[i] == "6" else ("PART" if type_flag_codes[i] == "7" else None)
        nm = names[i] if i < len(names) else None
        if nature_aligned:
            nat = nature_codes[i]
        else:
            nat = None
            if name_nature_dict is not None and nm and not nm.startswith("UNKNOWN_NAME["):
                nat = name_nature_dict.get(nm)
                if nat is not None:
                    used_name_lookup = True
            if nat is None and sigle_nature_dict is not None and sigles_aligned and raw_sigles[i]:
                nat = sigle_nature_dict.get(raw_sigles[i])
                if nat is not None:
                    used_sigle_lookup = True
            if nat is None and nm and not nm.startswith("UNKNOWN_NAME[") and _looks_like_university(nm):
                nat = "UNIV"
                used_keyword_fallback = True
        recs.append({
            "name": nm,
            "sigle": raw_sigles[i] if sigles_aligned else None,
            "type_code": type_code,
            "nature_code": nat,
            "bucket": bucket_historical(nat),  # None -> other_etab (conservative default, unchanged)
        })
    if used_name_lookup:
        flags.append("tutelle_nature_via_name_lookup")
    if used_sigle_lookup:
        flags.append("tutelle_nature_via_sigle_lookup")
    if used_keyword_fallback:
        flags.append("tutelle_class_keyword_fallback")
    return {"aligned": True, "flags": flags, "name_source": name_source, "tutelles": recs}


if __name__ == "__main__":
    # Self-test / corpus-wide sanity report (not part of the pipeline; run manually to verify).
    from common_io import RNSR_DIR, aprint

    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    sigle_dict = build_sigle_name_dict(active, historical)
    aprint(f"global sigle->name dictionary: {len(sigle_dict)} entries")

    n_active_aligned = 0
    n_active_unrecoverable = 0
    for _, row in active.iterrows():
        r = parse_active_row(row, sigle_dict)
        if r["aligned"]:
            n_active_aligned += 1
        if "tutelle_name_unrecoverable" in r.get("flags", []):
            n_active_unrecoverable += 1
    aprint(f"active: {n_active_aligned}/{len(active)} rows type/nature-aligned; "
           f"{n_active_unrecoverable} rows with unrecoverable names")

    n_hist_aligned = 0
    n_hist_unrecoverable = 0
    n_hist_nature_misaligned = 0
    for _, row in historical.iterrows():
        r = parse_historical_row(row, sigle_dict)
        if r["aligned"]:
            n_hist_aligned += 1
        if "tutelle_name_unrecoverable" in r.get("flags", []):
            n_hist_unrecoverable += 1
        if "historical_nature_code_misaligned" in r.get("flags", []):
            n_hist_nature_misaligned += 1
    aprint(f"historical: {n_hist_aligned}/{len(historical)} rows have a usable type flag; "
           f"{n_hist_unrecoverable} rows with unrecoverable names; "
           f"{n_hist_nature_misaligned} rows with misaligned nature codes")
