"""S9b fix cycle -- Finding 1 (CRIT): institution-name canonicalization table.

Builds `deliverable/institution_name_canonical.csv` from the CURRENT (pre-fix) master parquet's
5 tutelle-shaped columns (`universities_at_start`, `rto_tutelles`, `other_etab_tutelles`,
`participants_nontutelle`, `tutelles_raw_v2`). One row per distinct raw string found anywhere in
those columns, mapping it to a canonical spelling.

Grouping rule: EXACT-normalized-string-key only (`institution_canon.normalize_key` -- accent/case/
punctuation fold + stopword drop + token sort), NEVER fuzzy matching. Two raw strings that share a
key are candidate duplicates -- merged UNLESS the pair is protected by a genuine, dated rename/
merger event already in `staged/university_merger_crosswalk.csv` (a real institutional history
event, start-date-separated on purpose: predecessors keep their own historical name, never
collapsed into the successor).

A pair is "crosswalk-protected" only when a SINGLE crosswalk event's own `current_name_rnsr` and
one of its own `predecessor_names` reduce to the IDENTICAL normalized key (verified empirically:
this is exactly the Nantes and Paris-13 cases -- a coincidental key collision with an unrelated
event, e.g. Grenoble Alpes's 2016 merger row, does NOT protect a same-institution formatting
variant pair that has nothing to do with that event's actual predecessors).

Two hand-verified manual overrides (documented in staged/S9B_FIX_CHECKPOINT.md, NOT caught by
automatic key clustering because an extra token breaks the key match) and two hand-flagged
"needs_review, do not merge, could not verify without web access" pairs are layered on top -- see
the constants below.

Output columns: raw_name, canonical_name, uai, institution_type
(UNIV|EPST|EPIC|AUT_ETAB|HOSP|OTHER), needs_review, note, source_columns.

Idempotent: re-running overwrites the CSV from scratch; no state carried between runs beyond the
input files on disk.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_io import RNSR_DIR, RUN, STAGED, aprint  # noqa: E402
from institution_canon import STOPWORDS, normalize_key  # noqa: E402
from tutelle_align import (  # noqa: E402
    _split,
    build_name_nature_dict,
    build_sigle_name_dict,
    build_sigle_nature_dict,
)

DELIVERABLE = RUN / "deliverable"
OUT_CSV = DELIVERABLE / "institution_name_canonical.csv"

SOURCE_COLUMNS = [
    "universities_at_start", "rto_tutelles", "other_etab_tutelles",
    "participants_nontutelle", "tutelles_raw_v2",
]

# ---------------------------------------------------------------------------
# manual overrides (see staged/S9B_FIX_CHECKPOINT.md "Finding 1 fix design" / "CERSA special
# case" -- empirically verified this session against the live master + RNSR active/historical
# parquet + the crosswalk; re-deriving these would be wasted effort, reuse verbatim)
# ---------------------------------------------------------------------------

# raw_name -> canonical_name. Not caught by normalize_key clustering because the raw string
# carries an extra token ("2"/"paris2" or "EPE") that changes its key relative to the target.
MANUAL_CANONICAL_OVERRIDES: dict[str, str] = {
    # CERSA's own RNSR active.parquet record genuinely lists its one real tutelle twice under two
    # spellings; this override plus c08's general chain-collapse step (crosswalk-event-driven,
    # not CERSA-hardcoded) together fix components 865856:0 and 101069377:0. Target is the
    # crosswalk's own predecessor spelling for the Paris-Pantheon-Assas rename event (row 18 of
    # university_merger_crosswalk.csv).
    "Université Panthéon-Assas Paris 2": "Université Panthéon-Assas",
    # Bare vs "(EPE)" formatting split, verified via the clean <=2017/2018+ year split (same
    # pattern as the other 13 auto-clustered genuine merges) -- the crosswalk's own Montpellier
    # row already treats "(EPE)" as this identity's name from 2015 onward, so this is safe.
    "Université de Montpellier": "Université de Montpellier (EPE)",
}

# Pairs that COULD be duplicate spellings of the same institution but could not be verified
# locally (no web access this fix cycle, no crosswalk row, do not have the same normalize_key so
# generic clustering would never even flag them as a candidate on its own). Left UNMERGED,
# both members flagged needs_review=True. Recommend a future Legifrance check (out of scope here).
MANUAL_NEEDS_REVIEW_PAIRS: list[tuple[str, str]] = [
    ("Université Jean Monnet EPE", "Université Jean Monnet Saint-Étienne"),
    ("Université Toulouse Capitole EPE", "Université Toulouse 1 - Capitole"),
]

# institution_type closed-set overrides for institutions not found in the RNSR name_nature_dict
# at all (non-RNSR entities, or entities whose RNSR nature code doesn't map cleanly).
INSTITUTION_TYPE_MANUAL: dict[str, str] = {
    "Institut Pasteur": "OTHER",  # private foundation, non-RNSR entity pattern
    "Inria": "EPST",
    "CEA": "EPIC",
    "Collège de France": "AUT_ETAB",
    "EURECOM": "AUT_ETAB",
}

NATURE_CODE_TO_TYPE = {"UNIV": "UNIV", "UT": "UNIV", "EPST": "EPST", "EPIC": "EPIC", "MEDIC": "HOSP"}

# ---------------------------------------------------------------------------
# S9c fix cycle (2026-08-28), finding G: the S9a UAI-merge pass (5b below) still leaves CEA, Inria,
# EPHE, ESPCI, MNHN and Observatoire de la Cote d'Azur each split across 2 spellings (hostile
# review S9c section 6.2) -- in every case because the MINORITY spelling has no UAI recorded in
# name_uai_dict (it enters the raw-string pool from tutelles_raw_v2/an override, not from an RNSR
# tutelle field with a UAI attached) AND an extra token (a parenthetical acronym, "Paris", or a
# plural/de-variant) also changes its normalize_key, so step-4 clustering misses it too. Found by
# ASCII/accent-insensitive substring query -- never a hand-typed accented literal, same discipline
# as scripts/c04_crosswalk.py's resolve() -- and merged onto whichever matched spelling the
# `prefer` predicate selects (queries run against the FOLDED, already-clustered canonical strings,
# not raw strings, so this composes correctly with steps 1-5b above it).
MANUAL_MERGE_GROUPS_G: list[dict] = [
    {"name": "CEA", "query": "energie atomique et aux energies alternatives",
     "prefer": lambda f: "cea" not in f.split()},
    {"name": "Inria", "query": "recherche en informatique",
     "prefer": lambda f: "inria" not in f.split() and " en automatique" not in f},
    {"name": "EPHE", "query": "pratique des hautes etudes",
     "prefer": lambda f: "paris" in f.split()},
    {"name": "ESPCI", "query": "chimie industrielle",
     "prefer": lambda f: "industrielles" not in f.split()},
    {"name": "MNHN", "query": "histoire naturelle",
     "prefer": lambda f: "paris" in f.split()},
    {"name": "Observatoire de la Cote d'Azur", "query": "observatoire de la cote d azur",
     "prefer": lambda f: "nice" in f.split()},
]

# S9c fix cycle, finding G: the S9a UAI-merge pass (5b) collapsed exactly one documented crosswalk
# pair -- Universite Paris 13 - Paris Nord (predecessor, pre-2020) / Universite Paris Nord Paris 13
# (current_name_rnsr, the 2020-01-01 rename row in university_merger_crosswalk.csv) -- because both
# names share UAI 0931238R AND (unlike a genuine formatting-only variant) both ALSO reduce to the
# identical normalize_key, meaning build_protected_keys already correctly protects this pair at
# step 4, but step 5b's UAI merge (which runs on CURRENT canonical_of values, ignoring how they got
# there) re-merges it anyway. Fix: a uai group is exempt from the merge when ALL its canons pairwise
# reduce to the SAME protected key (i.e. it IS a crosswalk-documented dated identity split, not a
# mere RNSR active-vs-historical spelling variant like Tours/Savoie/the other 9).
PROTECTED_UAI_FROM_MERGE_NOTE = (
    "protected: this UAI group's canons reduce to a single normalize_key that is itself "
    "crosswalk-protected (a genuine dated rename/merger, not a formatting variant) -- left "
    "UNMERGED, unlike the other UAI collisions this run found (S9c fix cycle, finding G)."
)


def _fold(s: str) -> str:
    s2 = unicodedata.normalize("NFKD", s)
    s2 = "".join(c for c in s2 if not unicodedata.combining(c))
    s2 = re.sub(r"[^a-z0-9]+", " ", s2.lower())
    return re.sub(r"\s+", " ", s2).strip()


def apply_manual_merge_groups_g(canonical_of: dict[str, str], note_of: dict[str, str],
                                 needs_review_of: dict[str, bool], all_raw: list[str]) -> int:
    n_merged = 0
    for g in MANUAL_MERGE_GROUPS_G:
        qfold = _fold(g["query"])
        current_canons = sorted({canonical_of[r] for r in all_raw})
        matches = [c for c in current_canons if qfold in _fold(c)]
        if len(matches) < 2:
            aprint(f"[build_canon] manual_merge_group_g {g['name']}: {len(matches)} canonical "
                   f"match(es) for query={g['query']!r} -- nothing to merge"
                   + (f": {matches}" if matches else ""))
            continue
        preferred = [c for c in matches if g["prefer"](_fold(c))]
        rep = preferred[0] if preferred else sorted(matches)[0]
        aprint(f"[build_canon] manual_merge_group_g {g['name']}: {matches} -> {rep!r}")
        for raw in all_raw:
            if canonical_of[raw] in matches and canonical_of[raw] != rep:
                note_of[raw] = (f"manual_merge_group_g ({g['name']}, S9c fix G): merged with "
                                 f"'{rep}' -- same institution, a spelling/suffix/plural variant "
                                 f"the UAI-merge pass (5b) could not catch (no uai recorded for "
                                 f"the minority spelling, or an extra token like Paris/(CEA)/"
                                 f"(Inria) that also changes normalize_key)")
                canonical_of[raw] = rep
                needs_review_of[raw] = False
                n_merged += 1
    return n_merged


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def build_name_uai_dict(active: pd.DataFrame, historical: pd.DataFrame) -> dict[str, str]:
    """Global tutelle NAME -> most-common UAI, harvested ONLY from rows where the row's own
    names/type/nature/uai lists all align in length (same trust-only-fully-verified-rows
    construction as tutelle_align.build_name_nature_dict, just keyed on uai_des_tutelles).
    Stricter subset than build_name_nature_dict (uai lists are the least reliable of the four,
    per tutelle_align.py's own docstring), so coverage is intentionally partial -- blank uai in
    the output CSV is expected and fine for institutions never fully UAI-aligned."""
    counter: dict[str, Counter] = {}

    def _absorb(df: pd.DataFrame, type_col: str, nature_col: str):
        for tut, typ, nat, uai in zip(df["tutelles"].fillna(""), df[type_col].fillna(""),
                                       df[nature_col].fillna(""), df["uai_des_tutelles"].fillna("")):
            names = _split(tut)
            types = _split(typ)
            natures = _split(nat)
            uais = _split(uai)
            if not names or not (len(names) == len(types) == len(natures) == len(uais)):
                continue
            for n, u in zip(names, uais):
                if not n or not u:
                    continue
                counter.setdefault(n, Counter())[u] += 1

    _absorb(active, "code_de_type_de_tutelle", "code_de_nature_de_tutelle")
    _absorb(historical, "code_de_nature_de_tutelle", "code_de_type_de_tutelle")  # swapped semantics
    return {n: c.most_common(1)[0][0] for n, c in counter.items()}


def build_active_all_names(active: pd.DataFrame) -> set[str]:
    """Every TUTE-type tutelle name from active.parquet rows where names/type/nature all align
    (RNSR's own CURRENT, ground-truth spelling for any currently-existing tutelle-eligible
    institution -- university, RTO, or other établissement). Used to pick the preferred spelling
    within a genuine merge cluster (prefer RNSR's own current spelling over an older/differently-
    formatted variant)."""
    names: set[str] = set()
    for tut, typ, nat in zip(active["tutelles"].fillna(""), active["code_de_type_de_tutelle"].fillna(""),
                              active["code_de_nature_de_tutelle"].fillna("")):
        ns = _split(tut)
        ts = _split(typ)
        na = _split(nat)
        if not ns or not (len(ns) == len(ts) == len(na)):
            continue
        for n, t in zip(ns, ts):
            if t == "TUTE" and n:
                names.add(n)
    return names


def build_protected_keys(crosswalk: pd.DataFrame) -> set[str]:
    """A key is protected only when ONE crosswalk event's own current_name_rnsr and one of its
    own predecessor_names entries reduce to the IDENTICAL normalized key -- i.e. the event IS the
    formatting-looking pair (Nantes, Paris-13). A key that merely happens to equal some OTHER,
    unrelated event's current_name_rnsr (e.g. Grenoble Alpes's 2016 merger row, whose real
    predecessors are Joseph Fourier/Pierre Mendes France/Stendhal, nothing to do with a
    'de Grenoble Alpes' formatting variant) must NOT be protected -- verified empirically this
    session; a naive "key appears anywhere in the crosswalk" check over-protects and would wrongly
    block the genuine Grenoble Alpes merge."""
    protected: set[str] = set()
    for _, row in crosswalk.iterrows():
        cur = row["current_name_rnsr"]
        if not isinstance(cur, str):
            continue
        kcur = normalize_key(cur)
        for p in str(row["predecessor_names"]).split(";"):
            if not p:
                continue
            if normalize_key(p) == kcur:
                protected.add(kcur)
    return protected


def pick_canonical(members: list[str], active_all_names: set[str]) -> str:
    in_active = [m for m in members if m in active_all_names]
    if in_active:
        return sorted(in_active)[0]
    most_diacritics = sorted(members, key=lambda m: (-sum(1 for c in m if c != _strip_accents(c)), m))
    return most_diacritics[0]


def infer_institution_type(canonical_name: str, name_nature_dict: dict[str, str]) -> str:
    if canonical_name in INSTITUTION_TYPE_MANUAL:
        return INSTITUTION_TYPE_MANUAL[canonical_name]
    if canonical_name.startswith("["):
        return "OTHER"  # v2 numpy-array-repr passthrough artifact, out of scope to fix here
    code = name_nature_dict.get(canonical_name)
    if code is not None:
        return NATURE_CODE_TO_TYPE.get(code, "AUT_ETAB")
    folded = _strip_accents(canonical_name).lower()
    if any(k in folded for k in ("hopital", "chu ", "chr ", "chru ", "assistance publique")):
        return "HOSP"
    if "ministere" in folded:
        return "OTHER"
    if folded.strip().startswith("universit"):
        return "UNIV"
    return "OTHER"


def main() -> None:
    aprint("=== build_institution_canonical ===")

    master = pd.read_parquet(DELIVERABLE / "erc_france_attribution_master.parquet")
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    crosswalk = pd.read_csv(STAGED / "university_merger_crosswalk.csv", dtype=str)

    # ---- 1. extract distinct raw strings per column, track source columns ----
    # Idempotence: once c08_assemble_master.py has run this fix once, a tutelle-shaped column in
    # the master parquet holds CANONICAL values and the pre-canonicalization strings live in its
    # own <col>_raw sibling instead -- read THAT column when it exists so a second/future run of
    # this script (e.g. after a fresh RNSR snapshot) still gathers the FULL original raw-string
    # pool, not an already-shrunk one. First-ever run (the _raw column doesn't exist yet) falls
    # back to the column itself. S9a fix cycle, finding 2/3: this used to be special-cased for
    # universities_at_start ONLY (the sole column the S9b fix cycle canonicalized) -- now that
    # finding 2 canonicalizes all 4 tutelle-shaped columns, ALL FOUR need this same _raw fallback,
    # not just universities_at_start; missing it for the other 3 was a genuine bug (verified: it
    # caused build_institution_canonical.py <-> c08_assemble_master.py to OSCILLATE between two
    # different merge states across repeated runs instead of converging, because each run's
    # canon_map was built from an already-partially-merged, already-shrunk raw pool for those 3
    # columns).
    RAW_SIBLING_OF = {c: f"{c}_raw" for c in SOURCE_COLUMNS if c != "tutelles_raw_v2"}
    per_col: dict[str, set[str]] = {}
    for col in SOURCE_COLUMNS:
        raw_sibling = RAW_SIBLING_OF.get(col)
        src_col = raw_sibling if raw_sibling and raw_sibling in master.columns else col
        if src_col != col:
            aprint(f"[build_canon] {col}: master already canonicalized once -- reading "
                   f"{src_col} for the full pre-canonicalization pool")
        vals: set[str] = set()
        for v in master[src_col].dropna():
            vals.update(x for x in v.split(";") if x)
        per_col[col] = vals
    before_universities_at_start = len(per_col["universities_at_start"])

    source_columns_of: dict[str, list[str]] = defaultdict(list)
    for col in SOURCE_COLUMNS:
        for v in per_col[col]:
            source_columns_of[v].append(col)
    all_raw = sorted(source_columns_of)
    aprint(f"[build_canon] {len(all_raw)} distinct raw strings across {len(SOURCE_COLUMNS)} columns "
           f"({before_universities_at_start} from universities_at_start alone)")

    # ---- 2. RNSR ground-truth dictionaries (imported, not re-implemented) ----
    sigle_dict = build_sigle_name_dict(active, historical)
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)  # noqa: F841 (kept for parity/future use)
    name_uai_dict = build_name_uai_dict(active, historical)
    active_all_names = build_active_all_names(active)
    aprint(f"[build_canon] RNSR dicts: name_nature={len(name_nature_dict)} name_uai={len(name_uai_dict)} "
           f"active_all_names={len(active_all_names)}")

    # ---- 3. crosswalk-protected keys ----
    protected_keys = build_protected_keys(crosswalk)
    aprint(f"[build_canon] {len(protected_keys)} crosswalk-protected normalized keys: {sorted(protected_keys)}")

    # ---- 4. cluster by normalized key ----
    clusters: dict[str, list[str]] = defaultdict(list)
    for raw in all_raw:
        clusters[normalize_key(raw)].append(raw)

    canonical_of: dict[str, str] = {}
    needs_review_of: dict[str, bool] = {}
    note_of: dict[str, str] = {}
    n_genuine_merge_members = 0
    n_protected_pairs = 0

    for key, members in clusters.items():
        if len(members) == 1:
            m = members[0]
            canonical_of[m] = m
            needs_review_of[m] = False
            note_of[m] = ""
            continue
        if key in protected_keys:
            n_protected_pairs += 1
            for m in members:
                canonical_of[m] = m
                needs_review_of[m] = False
                note_of[m] = ("protected: matches a dated rename/merger event in "
                               "staged/university_merger_crosswalk.csv -- NOT merged, "
                               "start-date semantics preserved (predecessor keeps its own name)")
            continue
        canon = pick_canonical(members, active_all_names)
        n_genuine_merge_members += len(members)
        for m in members:
            canonical_of[m] = canon
            needs_review_of[m] = False
            note_of[m] = (f"merged formatting/spelling variant of the same institution "
                           f"(accent/case/hyphen/word-order split, verified not crosswalk-protected); "
                           f"canonical spelling '{canon}'"
                           + ("" if m == canon else ""))

    # ---- 5. manual overrides (applied AFTER automatic clustering, may re-point a canonical) ----
    for raw, target in MANUAL_CANONICAL_OVERRIDES.items():
        if raw not in canonical_of:
            aprint(f"[build_canon] WARNING manual override raw_name not found in data: {raw!r}")
            continue
        canonical_of[raw] = target
        needs_review_of[raw] = False
        note_of[raw] = (f"manual override (S9b fix cycle): RNSR's own active-snapshot record for this "
                         f"structure lists its one tutelle twice under two spellings; mapped to the "
                         f"crosswalk's predecessor spelling '{target}' -- see PHASE_C_REPORT.md 'S9b fix "
                         f"cycle' section for the CERSA/Montpellier detail")
        n_genuine_merge_members += 1
    # safety: resolve one extra hop in case an override target is itself remapped (not expected
    # given the current override set, but keeps this robust to future additions)
    for raw in list(canonical_of):
        target = canonical_of[raw]
        if target in canonical_of and canonical_of[target] != target:
            canonical_of[raw] = canonical_of[target]

    # ---- 5b. S9a fix cycle, finding 3: UAI-based merge (hostile review F20) -- the RNSR UAI is
    # the ground-truth legal-entity key. normalize_key clustering can only ever catch variants that
    # share a token multiset, so it structurally misses different words for one entity (Universite
    # de Tours vs Universite Francois-Rabelais), abbreviation-vs-expansion (Grenoble INP vs Institut
    # polytechnique de Grenoble) or an extra token (Institut Curie vs Institut Curie Paris). Grouping
    # every raw_name's OWN (post-manual-override) canonical name by its uai catches all 12 such
    # collisions this run found (Tours 0370800U, Savoie 0730858L, Paris13 0931238R + 9 more: Inria,
    # CNES, Institut Curie, IPGP, Grenoble INP, ENS Mecanique Besancon, Chimie ParisTech,
    # AgroParisTech, EHESS). Runs AFTER the manual overrides (not before -- verified this matters:
    # running it before them double-merged the CERSA pair, 'Universite Panthéon-Assas' / 'Universite
    # Panthéon-Assas Paris 2', into the WRONG direction because they share a uai too, fighting the
    # manual override's own CERSA-specific direction; running here, that pair's canonical_of values
    # already agree post-override, so its uai group naturally collapses to len==1 and is skipped).
    # This pass supersedes normalize_key's own 'protected:' flag for Universite Paris Nord Paris 13 /
    # Universite Paris 13 - Paris Nord specifically -- verified (S9a review) that pair's crosswalk
    # row is itself DOCUMENTATION-ONLY (a real-world "Sorbonne Paris Nord" rename RNSR never adopted;
    # both spellings are simply RNSR's own active-vs-historical spelling of ONE UAI-identical entity,
    # the exact same mechanism as Tours/Savoie), not a genuine dated identity split -- so merging it
    # is correct, unlike a true crosswalk-protected pair (Nantes, Sorbonne, Universite de Paris, ...)
    # where the SAME uai would legitimately need to stay split by start-date. No such genuine case
    # exists among the 12 collisions found on this run's data (verified one by one against
    # university_merger_crosswalk.csv); this pass is unconditional and will need a documented
    # exception added here if a future RNSR/crosswalk refresh ever introduces one.
    uai_of_canon: dict[str, str] = {}
    for raw in all_raw:
        c = canonical_of[raw]
        if c not in uai_of_canon:
            uai_of_canon[c] = name_uai_dict.get(c, "")
    uai_groups: dict[str, set[str]] = defaultdict(set)
    for c, u in uai_of_canon.items():
        if u:
            uai_groups[u].add(c)
    n_uai_merges = 0
    n_uai_collision_groups = 0
    for uai, canons in uai_groups.items():
        if len(canons) < 2:
            continue
        # S9c fix cycle, finding G: skip a group whose canons ALL pairwise reduce to a single
        # crosswalk-PROTECTED normalize_key -- that means the "collision" is actually a genuine
        # dated identity split (predecessor/successor of a real rename/merger event) which
        # build_protected_keys already correctly kept apart at step 4; the UAI merge must not
        # override that protection (this is exactly the Paris-13/0931238R pair the hostile review
        # found wrongly collapsed -- Universite Paris 13 - Paris Nord / Universite Paris Nord
        # Paris 13, event 2020-01-01).
        canon_keys = {normalize_key(c) for c in canons}
        if len(canon_keys) == 1 and next(iter(canon_keys)) in protected_keys:
            aprint(f"[build_canon] uai_merge {uai}: {sorted(canons)} -- SKIPPED, crosswalk-protected "
                   f"(S9c fix G)")
            for c in canons:
                for raw in all_raw:
                    if canonical_of[raw] == c:
                        note_of[raw] = PROTECTED_UAI_FROM_MERGE_NOTE
            continue
        n_uai_collision_groups += 1
        rep = pick_canonical(sorted(canons), active_all_names)
        aprint(f"[build_canon] uai_merge {uai}: {sorted(canons)} -> '{rep}'")
        for raw in all_raw:
            if canonical_of[raw] in canons and canonical_of[raw] != rep:
                note_of[raw] = (f"uai_merged: RNSR UAI {uai} shared with '{rep}' -- same legal "
                                 f"entity, active-vs-historical/formatting spelling variant only; "
                                 f"verified not a crosswalk-protected dated identity split "
                                 f"(S9a fix cycle finding 3)")
                canonical_of[raw] = rep
                needs_review_of[raw] = False
                n_uai_merges += 1
    aprint(f"[build_canon] UAI-based merge: {n_uai_collision_groups} collision group(s), "
           f"{n_uai_merges} raw_name row(s) repointed")

    # ---- 5c. S9c fix cycle, finding G: manual merge groups for the RTO/ecole spellings the UAI
    # merge (5b) could not close (CEA, Inria, EPHE, ESPCI, MNHN, Observatoire de la Cote d'Azur) ----
    n_manual_merge_g = apply_manual_merge_groups_g(canonical_of, note_of, needs_review_of, all_raw)
    aprint(f"[build_canon] manual merge groups (S9c fix G): {n_manual_merge_g} raw_name row(s) repointed")

    # S9c fix cycle, finding G (stale note): fix 4 of the S9a fix cycle added crosswalk rows for
    # BOTH pairs below (Universite Jean Monnet EPE/Saint-Etienne, Universite Toulouse Capitole EPE/
    # Universite Toulouse 1 - Capitole) -- the "no matching crosswalk row" note was true when
    # written and is false now. Checked dynamically (not hand-toggled) against the crosswalk
    # actually loaded this run, so this self-heals for any future pair too: if a crosswalk row's
    # own current_name_rnsr/predecessor_names now covers the pair, it is a VERIFIED dated identity
    # split (needs_review=False, protected-style note), not an unverified guess.
    for a, b in MANUAL_NEEDS_REVIEW_PAIRS:
        pair_keys = {normalize_key(a), normalize_key(b)}
        covered_by_crosswalk = False
        for _, cw_row in crosswalk.iterrows():
            cur = cw_row["current_name_rnsr"]
            if not isinstance(cur, str):
                continue
            preds = [p for p in str(cw_row["predecessor_names"]).split(";") if p]
            row_keys = {normalize_key(cur)} | {normalize_key(p) for p in preds}
            if pair_keys <= row_keys:
                covered_by_crosswalk = True
                break
        for m in (a, b):
            if m not in canonical_of:
                aprint(f"[build_canon] WARNING needs_review pair member not found in data: {m!r}")
                continue
            other = b if m == a else a
            if covered_by_crosswalk:
                needs_review_of[m] = False
                note_of[m] = (f"protected: '{m}' / '{other}' is a documented dated rename/merger "
                               f"event in staged/university_merger_crosswalk.csv (added by the S9a "
                               f"fix cycle's crosswalk-coverage fix) -- NOT merged, start-date "
                               f"semantics preserved (S9c fix G corrected a stale 'no matching "
                               f"crosswalk row' note here)")
            else:
                needs_review_of[m] = True
                note_of[m] = (f"needs_review: possible undocumented rename/status change vs "
                               f"'{other}' (no matching crosswalk row, could not verify without "
                               f"web access this fix cycle) -- recommend a future Legifrance/"
                               f"RNSR-fiche check; NOT merged")

    # ---- 6. institution_type + uai ----
    rows = []
    for raw in all_raw:
        canon = canonical_of[raw]
        itype = infer_institution_type(canon, name_nature_dict)
        uai = name_uai_dict.get(canon, "")
        rows.append({
            "raw_name": raw,
            "canonical_name": canon,
            "uai": uai,
            "institution_type": itype,
            "needs_review": needs_review_of[raw],
            "note": note_of[raw],
            "source_columns": ";".join(sorted(source_columns_of[raw])),
        })

    out = pd.DataFrame(rows).sort_values(["canonical_name", "raw_name"]).reset_index(drop=True)
    DELIVERABLE.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    # ---- 7. summary (before/after distinct-universities count for universities_at_start) ----
    after_universities_at_start = len({canonical_of[r] for r in per_col["universities_at_start"]})
    n_needs_review = sum(1 for v in needs_review_of.values() if v)
    aprint(f"[build_canon] wrote {OUT_CSV} ({len(out)} rows)")
    aprint(f"[build_canon] universities_at_start distinct: {before_universities_at_start} (raw) -> "
           f"{after_universities_at_start} (canonical)")
    aprint(f"[build_canon] genuine merge cluster members (incl. manual overrides): {n_genuine_merge_members}, "
           f"crosswalk-protected pairs left unmerged: {n_protected_pairs}, needs_review rows: {n_needs_review}")
    aprint("build_institution_canonical done.")


if __name__ == "__main__":
    main()
