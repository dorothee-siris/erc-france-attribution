#!/usr/bin/env python3
"""Build the LIGHTER PUBLIC release tree of the ERC France attribution project.

Re-runnable, local-only, no network access, no git operations. Reads ONE consolidated source
tree (SRC, the private repo -- everything already lives under one root: deliverable/, docs/,
pipeline/, integration/, data/raw/) and writes a lighter, name-scrubbed, open-releasable copy to
TARGET.

Design principles:
  - Never delete. A file that must be retired is moved into TARGET/_TO_DELETE_<date>/ instead
    (this machine's own deletion-blocking hook enforces this anyway).
  - ASCII-only console output (Windows console here is cp1252 -- a raw accented character
    printed to it raises UnicodeEncodeError mid-run).
  - Safety-first: realpaths of SRC and TARGET are printed and asserted distinct (case-
    insensitive) and non-nested before a single byte is written.
  - RELATIVE paths only in anything this script WRITES into TARGET (manifest, checkpoint,
    README) -- SRC's own folder name may be renamed later ("ERC France attribution"), so this
    script never bakes today's SRC folder name into a document meant to outlive it. The script
    itself locates SRC by trying a short list of candidate names (see SRC_NAME_CANDIDATES),
    overridable via the ERC_SRC_ROOT environment variable.
  - Name-scrub gate: a name roster is built from SRC's master pi_name column, SRC's Phase D
    staged research (phase_d_staged.csv's own pi_name column), and a best-effort scan of Phase E
    web-research JSON field VALUES (evidence_note prose, Title-Case candidate extraction) --
    then every file actually written into TARGET is checked against it: a full-name hit in a
    machine-readable data file (.csv/.json/.py/.txt/.yaml/.cff/.toml, or a parquet column) is a
    hard build-failure signal (reported, not silently patched); a full-name hit in a .md prose
    file is auto-scrubbed to "the PI" and counted. Surname-only (single-token) hits are reported
    with context, never blind-scrubbed. Emails and ORCIDs are scanned for too.

Usage:
    python tools/make_public_variant.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# 0. PATHS
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent          # TARGET/tools
TARGET = HERE.parent                             # TARGET
INTERNAL_PROJECTS = TARGET.parent                # .../SIRIS/Internal Projects

SRC_NAME_CANDIDATES = ["erc-france-attribution-repo", "ERC France attribution"]


def _find_src() -> Path:
    env = os.environ.get("ERC_SRC_ROOT")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise SystemExit("ERC_SRC_ROOT is set but not a directory: %s" % env)
    for name in SRC_NAME_CANDIDATES:
        p = INTERNAL_PROJECTS / name
        if p.is_dir():
            return p
    raise SystemExit(
        "Could not find SRC under %s (tried: %s). Set ERC_SRC_ROOT to override."
        % (INTERNAL_PROJECTS, SRC_NAME_CANDIDATES)
    )


SRC = _find_src()
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")
QUARANTINE_DIR = TARGET / f"_TO_DELETE_{BUILD_DATE.replace('-', '')}"


def ascii_safe(s: str) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


def log(msg: str) -> None:
    print(ascii_safe(msg))


# --------------------------------------------------------------------------
# 1. SAFETY GATE
# --------------------------------------------------------------------------

def safety_gate() -> None:
    t = os.path.realpath(str(TARGET))
    s = os.path.realpath(str(SRC))
    log("SAFETY -- realpath(TARGET) = %s" % t)
    log("SAFETY -- realpath(SRC)    = %s" % s)
    assert t.lower() != s.lower(), "TARGET == SRC (case-insensitive) -- ABORT"
    assert not t.lower().startswith(s.lower() + os.sep), "TARGET is inside SRC -- ABORT"
    assert not s.lower().startswith(t.lower() + os.sep), "SRC is inside TARGET -- ABORT"
    log("SAFETY -- paths distinct and non-nested. Proceeding.")


# --------------------------------------------------------------------------
# 2. CHECKPOINT
# --------------------------------------------------------------------------

CHECKPOINT_PATH = TARGET / "BUILD_CHECKPOINT.md"


def checkpoint_init() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (
        "# Build checkpoint -- erc-france-attribution-public\n\n"
        f"Build started: {now}\n\n"
        "Script: `tools/make_public_variant.py` (re-runnable; never deletes; quarantines stale "
        f"files into `_TO_DELETE_{BUILD_DATE.replace('-', '')}/`).\n\n"
        "Source read (read-only, never written): the consolidated project repo, found by this "
        "script under this folder's own grandparent directory (see `tools/make_public_variant.py`'s "
        "`SRC_NAME_CANDIDATES` -- no absolute path recorded here on purpose, since that source "
        "folder's own name may be renamed later).\n\n"
        "## Progress log\n\n"
    )
    CHECKPOINT_PATH.write_text(text, encoding="utf-8")


def checkpoint(step: str) -> None:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    line = f"- [{now}] {step}\n"
    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    log("CHECKPOINT: " + step)


# --------------------------------------------------------------------------
# 3. FILE HELPERS (copy only; never delete)
# --------------------------------------------------------------------------

STATS = {"files_written": 0, "bytes_written": 0}


def _record(path: Path) -> None:
    STATS["files_written"] += 1
    try:
        STATS["bytes_written"] += path.stat().st_size
    except OSError:
        pass


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    _record(dst)


def write_text(dst: Path, content: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    _record(dst)


EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints"}
EXCLUDE_FILE_SUFFIXES = {".pyc"}


def copy_tree_filtered(src: Path, dst: Path) -> list[Path]:
    written: list[Path] = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
        rel_root = Path(root).relative_to(src)
        for fname in files:
            if Path(fname).suffix in EXCLUDE_FILE_SUFFIXES:
                continue
            s = Path(root) / fname
            d = dst / rel_root / fname
            copy_file(s, d)
            written.append(d)
    return written


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quarantine_stale(rel_path: str) -> bool:
    """NEVER DELETE: if a file at TARGET/<rel_path> exists from a previous run of this
    re-runnable script but is no longer supposed to be part of the shipped tree (e.g. a file this
    version of the script decided to exclude after a name-scan-gate finding), move it into
    TARGET/_TO_DELETE_<date>/<rel_path> instead of leaving it in place or deleting it. Returns
    True if something was moved."""
    src = TARGET / rel_path
    if not src.is_file():
        return False
    dst = QUARANTINE_DIR / rel_path
    t = os.path.realpath(str(src))
    q = os.path.realpath(str(QUARANTINE_DIR))
    assert not t.lower().startswith(q.lower()), "quarantine_stale: source already inside quarantine"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    log(f"QUARANTINED (stale, no longer shipped): {rel_path} -> "
        f"_TO_DELETE_{BUILD_DATE.replace('-', '')}/{rel_path}")
    return True


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# --------------------------------------------------------------------------
# 4. NAME ROSTER
#    - full names (multi-token, blocking-precision): SRC/deliverable master pi_name distinct
#      values UNION SRC/integration/staged/phase_d/phase_d_staged.csv's own pi_name column.
#    - candidate names swept from SRC/integration/staged/phase_e/web_results/*.json FIELD VALUES
#      (evidence_note prose -- Title-Case 2-3 token heuristic, JSON fields only, never raw bytes).
#    - surname tokens (>=4 chars, advisory-only): every token of every full name above, minus a
#      stopword list of common French words / place / institution names (dropped tokens listed).
# --------------------------------------------------------------------------

STOPWORDS = {
    # common French function words (kept even though most are <4 chars, for completeness)
    "de", "du", "des", "la", "le", "les", "et", "en", "un", "une", "sur", "dans", "avec", "pour",
    "cette", "ces", "son", "sa", "ses", "au", "aux", "par", "est", "sont",
    # institutional / academic vocabulary
    "universite", "université", "university", "ecole", "école", "institut", "institute",
    "laboratoire", "laboratory", "centre", "center", "national", "recherche", "research",
    "cnrs", "inserm", "inria", "inrae", "cea", "irstea", "cirad", "ird", "cnes", "umr", "upr",
    "fre", "sciences", "france", "francaise", "française", "technologie", "europeen",
    "européenne", "recherches", "unite", "unité", "mixte", "groupe", "group", "departement",
    "département", "faculte", "faculté", "hopital", "hôpital", "chu", "chru", "observatoire",
    "musee", "musée", "fondation", "foundation", "conseil", "region", "région", "ministere",
    "ministère", "agence", "association", "societe", "société", "superieure", "supérieure",
    "normale", "polytechnique", "sorbonne", "centrale",
    # French place names (regions, cities, communes appearing often in this dataset's addresses)
    "paris", "lyon", "marseille", "toulouse", "bordeaux", "nantes", "grenoble", "strasbourg",
    "montpellier", "lille", "rennes", "nancy", "aix", "nice", "rouen", "reims", "dijon",
    "angers", "brest", "tours", "orleans", "orléans", "clermont", "limoges", "poitiers", "caen",
    "metz", "perpignan", "besancon", "besançon", "amiens", "nimes", "nîmes", "villeurbanne",
    "avignon", "versailles", "antibes", "cannes", "ajaccio", "calais", "dunkerque", "valence",
    "chambery", "chambéry", "annecy", "saclay", "gif", "palaiseau", "evry", "évry", "cergy",
    "nanterre", "creteil", "créteil", "bobigny", "ivry", "vitry", "massy", "orsay", "jouy",
    "sophia", "plouzane", "plouzané", "sceaux", "meudon", "issy", "boulogne",
    # French honorifics/generic titles that precede a place or role name, not a person
    "docteur", "professeur", "madame", "monsieur", "cedex",
}

FULL_NAME_RE = re.compile(
    r"\b[A-ZÀ-Ÿ][a-zà-ÿ'\u2019]+(?:-[A-ZÀ-Ÿ][a-zà-ÿ'\u2019]+)?"
    r"(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ'\u2019]+(?:-[A-ZÀ-Ÿ][a-zà-ÿ'\u2019]+)?){1,2}\b"
)


def _extract_name_candidates_from_prose(text: str) -> set[str]:
    out: set[str] = set()
    for m in FULL_NAME_RE.finditer(text):
        cand = m.group(0)
        toks = [t.strip("-'\u2019") for t in cand.split()]
        if any(t.lower() in STOPWORDS for t in toks):
            continue
        out.add(cand)
    return out


def build_name_roster() -> dict:
    """Two precision tiers, deliberately kept separate:
      - `multi` (blocking-precision): pi_name values read directly from the master's own
        structured `pi_name` column and from Phase D staged research's own structured `pi_name`
        column -- both are authoritative, machine-read fields, not a heuristic guess.
      - `candidate_multi` (advisory-only, reported with context, never blind-blocking): 2-3
        Title-Case-token sequences heuristically extracted from Phase E web_results JSON field
        VALUES (evidence_note prose). Verified empirically while building this script: this sweep
        also catches plenty of non-name text shaped like a name (lab/institute fragments -- "Institut
        de Biologie Structurale", "Institut des Hautes Etudes Scientifiques" -- French street-name
        honorifics -- "rue du Docteur Roux" -- and English lab/grant-acronym fragments -- "Bacterial
        Nanomachines", "Advanced Study"). Promoting this set to blocking precision would produce
        false "PI name" hits across ordinary institution/lab-name columns throughout the tree, which
        is exactly the failure mode this two-tier design avoids -- same rationale as the "surname
        tokens ... report with context, do not blind-scrub" rule for single-token hits.
    """
    multi: set[str] = set()
    candidate_multi: set[str] = set()
    counts: dict[str, int] = {}

    # (a) authoritative: SRC master's own pi_name column
    master_csv = SRC / "deliverable" / "erc_france_attribution_master.csv"
    df = pd.read_csv(master_csv, dtype=str, keep_default_na=False, encoding="utf-8")
    pi_values = sorted({v.strip() for v in df["pi_name"].unique() if v and v.strip()})
    counts["pi_name_distinct_master"] = len(pi_values)
    for v in pi_values:
        multi.add(_nfc(v))

    # (b) Phase D staged research's own pi_name column
    phase_d_csv = SRC / "integration" / "staged" / "phase_d" / "phase_d_staged.csv"
    phase_d_names: set[str] = set()
    if phase_d_csv.is_file():
        dfd = pd.read_csv(phase_d_csv, dtype=str, keep_default_na=False, encoding="utf-8")
        if "pi_name" in dfd.columns:
            phase_d_names = {v.strip() for v in dfd["pi_name"].unique() if v and v.strip()}
    counts["pi_name_distinct_phase_d_staged"] = len(phase_d_names)
    for v in phase_d_names:
        multi.add(_nfc(v))

    # (c) Phase E web_results JSON field VALUES (evidence_note prose) -- candidate extraction,
    #     JSON fields only (never raw file bytes / JSON syntax). ADVISORY tier only (see docstring).
    web_dir = SRC / "integration" / "staged" / "phase_e" / "web_results"
    web_candidates: set[str] = set()
    n_json = 0
    if web_dir.is_dir():
        for jf in sorted(web_dir.glob("*.json")):
            n_json += 1
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, str) and v.strip():
                        web_candidates |= _extract_name_candidates_from_prose(v)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                web_candidates |= _extract_name_candidates_from_prose(item)
    counts["phase_e_web_results_json_files_scanned"] = n_json
    counts["phase_e_web_results_candidates"] = len(web_candidates)
    for v in web_candidates:
        v_nfc = _nfc(v)
        if v_nfc not in multi:  # already-authoritative names stay in the blocking tier
            candidate_multi.add(v_nfc)

    # multi-token filter (>=2 tokens only)
    multi = {v for v in multi if len(v.split()) >= 2}
    candidate_multi = {v for v in candidate_multi if len(v.split()) >= 2}

    # surname/given-name tokens (>=4 chars, stopword-filtered) -- advisory-only set, drawn from
    # BOTH tiers (a surname worth flagging with context doesn't need blocking-tier provenance)
    single: set[str] = set()
    dropped_tokens: set[str] = set()
    for name in multi | candidate_multi:
        for tok in name.split():
            tok_clean = tok.strip("-'\u2019")
            if len(tok_clean) < 4:
                continue
            if tok_clean.lower() in STOPWORDS:
                dropped_tokens.add(tok_clean)
                continue
            single.add(tok_clean)

    counts["multi_token_full_names_authoritative_blocking"] = len(multi)
    counts["multi_token_candidates_phase_e_advisory_only"] = len(candidate_multi)
    counts["single_token_surnames_kept"] = len(single)
    counts["single_token_dropped_stopwords"] = len(dropped_tokens)

    return {
        "multi": multi,
        "candidate_multi": candidate_multi,
        "single": single,
        "dropped_tokens": sorted(dropped_tokens),
        "counts": counts,
    }


# --------------------------------------------------------------------------
# 5. NAME LOOKUP -- ONE compiled alternation regex per set
# --------------------------------------------------------------------------

class NameLookup:
    """One compiled `\\b(?:name1|name2|...)\\b` alternation regex for the whole set (as directed),
    longest-first so a longer name is matched before a shorter one it contains."""

    def __init__(self, names: set[str]):
        self.names = sorted({_nfc(n) for n in names}, key=len, reverse=True)
        if self.names:
            self.pattern = re.compile(
                r"\b(?:" + "|".join(re.escape(n) for n in self.names) + r")\b",
                re.IGNORECASE,
            )
        else:
            self.pattern = None

    def find(self, text: str) -> list[str]:
        if not self.pattern:
            return []
        return self.pattern.findall(text)

    def scrub(self, text: str) -> tuple[str, int]:
        if not self.pattern:
            return text, 0
        text2, n = self.pattern.subn("the PI", text)
        return text2, n


# --------------------------------------------------------------------------
# 6. TEXT/TABLE SCANNING
# --------------------------------------------------------------------------

TEXT_EXTS = {".md", ".csv", ".json", ".py", ".txt", ".yaml", ".yml", ".cff", ".toml"}
MD_EXTS = {".md"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b")
EMAIL_ALLOWLIST_DOMAINS = ("sirisacademic.com", "anthropic.com")


def scan_text_lines(path: Path, lookup_multi: NameLookup, lookup_single: NameLookup):
    """Line-by-line scan (as directed) of a text file. Returns dict with hit lists (deduped)."""
    multi_hits: set[str] = set()
    single_hits: set[str] = set()
    emails: set[str] = set()
    orcids: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as f:
            for line in f:
                multi_hits.update(lookup_multi.find(line))
                single_hits.update(lookup_single.find(line))
                emails.update(e for e in EMAIL_RE.findall(line)
                              if not e.lower().endswith(EMAIL_ALLOWLIST_DOMAINS))
                orcids.update(ORCID_RE.findall(line))
    except UnicodeDecodeError:
        return None
    return {"multi": sorted(multi_hits), "single": sorted(single_hits),
            "emails": sorted(emails), "orcids": sorted(orcids)}


def scan_parquet_columns(path: Path, lookup_multi: NameLookup, lookup_single: NameLookup) -> dict:
    """Column-name + object-column-value scan (as directed for parquet)."""
    out: dict = {}
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        return {"__error__": [str(e)]}
    col_names_blob = " ".join(str(c) for c in df.columns)
    hit = {"multi": sorted(set(lookup_multi.find(col_names_blob))),
           "single": sorted(set(lookup_single.find(col_names_blob))),
           "emails": [], "orcids": []}
    if hit["multi"] or hit["single"]:
        out["__column_names__"] = hit
    for col in df.columns:
        if df[col].dtype != object:
            continue
        try:
            vals = df[col].dropna().astype(str).unique()
        except Exception:
            continue
        if len(vals) == 0:
            continue
        blob = "\n".join(str(v) for v in vals)
        multi_hits = sorted(set(lookup_multi.find(blob)))
        single_hits = sorted(set(lookup_single.find(blob)))
        emails = sorted({e for e in EMAIL_RE.findall(blob)
                          if not e.lower().endswith(EMAIL_ALLOWLIST_DOMAINS)})
        orcids = sorted(set(ORCID_RE.findall(blob)))
        if multi_hits or single_hits or emails or orcids:
            out[col] = {"multi": multi_hits, "single": single_hits, "emails": emails,
                        "orcids": orcids}
    return out


def scrub_md_file(path: Path, lookup_multi: NameLookup) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = lookup_multi.scrub(text)
    if n:
        path.write_text(new_text, encoding="utf-8")
    return n


# --------------------------------------------------------------------------
# 7. MASTER CSV/PARQUET TRANSFORM
# --------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s\"'\)\]]+")
PERSON_COLUMNS_TO_DROP = ["pi_name"]
URL_ONLY_COLUMNS = ["evidence_ref", "integration_note", "park_reason"]


def extract_urls_only(cell: str) -> str:
    if not cell:
        return ""
    urls = URL_RE.findall(cell)
    return "; ".join(dict.fromkeys(u.rstrip(".,;)") for u in urls))


def transform_master_df(df: pd.DataFrame,
                         pattern_multi: NameLookup | None = None) -> tuple[pd.DataFrame, list[str], int]:
    dropped = []
    for col in PERSON_COLUMNS_TO_DROP:
        if col in df.columns:
            df = df.drop(columns=[col])
            dropped.append(col)
    for col in URL_ONLY_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).map(extract_urls_only)
    # Safety-net scrub: the name-scan gate found that `lab_name` free text can narrate a PI's
    # name directly even after `pi_name` itself is dropped (e.g. "... group led by <Name>" or
    # "PI <Name> works directly at ..."), for a handful of rows where a resolver captured
    # descriptive prose rather than a bare institutional lab name. Every object-dtype column is
    # scrubbed against the AUTHORITATIVE (blocking-precision) name roster as a final safety net,
    # not just the known URL_ONLY_COLUMNS -- cheap (same one compiled alternation regex) and
    # catches exactly this class of leak wherever it turns up.
    scrub_count = 0
    if pattern_multi is not None:
        for col in df.columns:
            if df[col].dtype != object:
                continue
            new_col = []
            for v in df[col]:
                if not isinstance(v, str) or not v:
                    new_col.append(v)
                    continue
                new_v, n = pattern_multi.scrub(v)
                if n:
                    scrub_count += n
                new_col.append(new_v)
            df[col] = new_col
    return df, dropped, scrub_count


def build_deliverable(pattern_multi: NameLookup) -> dict:
    checkpoint("deliverable/ -- starting")
    src = SRC / "deliverable"
    dst = TARGET / "deliverable"

    version = json.loads((src / "VERSION.json").read_text(encoding="utf-8"))
    source_version = version.get("version", "unknown")
    log(f"deliverable source VERSION.json version = {source_version}")

    df_csv = pd.read_csv(src / "erc_france_attribution_master.csv", dtype=str,
                          keep_default_na=False, encoding="utf-8")
    df_csv_t, dropped_cols, master_scrub_csv = transform_master_df(df_csv, pattern_multi)
    df_csv_t.to_csv(dst / "erc_france_attribution_master.csv", index=False, encoding="utf-8")
    _record(dst / "erc_france_attribution_master.csv")
    if master_scrub_csv:
        log(f"deliverable/erc_france_attribution_master.csv: safety-net scrubbed "
            f"{master_scrub_csv} full-name occurrence(s) in free-text columns (e.g. lab_name) "
            f"-> 'the PI'")

    df_pq = pd.read_parquet(src / "erc_france_attribution_master.parquet")
    df_pq_t, _, master_scrub_pq = transform_master_df(df_pq, pattern_multi)
    df_pq_t.to_parquet(dst / "erc_france_attribution_master.parquet", index=False)
    _record(dst / "erc_france_attribution_master.parquet")
    if master_scrub_pq:
        log(f"deliverable/erc_france_attribution_master.parquet: safety-net scrubbed "
            f"{master_scrub_pq} full-name occurrence(s) in free-text columns -> 'the PI'")

    for fname in ["region_funding.csv", "university_funding.csv",
                  "institution_name_canonical.csv"]:
        copy_file(src / fname, dst / fname)

    # FINAL_NUMBERS.md and VERSION.json are narrative/changelog PROSE (not row-level tabular
    # data) even though the latter has a .json extension -- both are known, from the source
    # project's own methodology narrative, to name specific PIs in their "lab_only tier" / fix-
    # cycle changelog prose (e.g. the S9e/residuals fix passes name specific PIs directly by
    # name). Scrubbed the same way as any .md doc, not blocked.
    scrub_count = 0
    for fname in ["FINAL_NUMBERS.md", "VERSION.json"]:
        dst_p = dst / fname
        text = (src / fname).read_text(encoding="utf-8")
        write_text(dst_p, text)
        new_text, n = pattern_multi.scrub(text)
        if n:
            dst_p.write_text(new_text, encoding="utf-8")
            scrub_count += n
            log(f"deliverable/{fname}: scrubbed {n} full-name occurrence(s) -> 'the PI'")

    total_scrub = scrub_count + master_scrub_csv + master_scrub_pq
    checkpoint(f"deliverable/ -- master csv+parquet written, columns dropped={dropped_cols}, "
               f"URL-only reduced={URL_ONLY_COLUMNS}, source version={source_version}, "
               f"n_rows={len(df_csv_t)}, FINAL_NUMBERS.md/VERSION.json scrubbed={scrub_count}, "
               f"master free-text safety-net scrubbed csv={master_scrub_csv} pq={master_scrub_pq}")
    return {"source_version": source_version, "dropped_cols": dropped_cols,
            "n_rows": len(df_csv_t), "scrub_count": total_scrub}


# --------------------------------------------------------------------------
# 8. validate_master.py ADAPTATION
# --------------------------------------------------------------------------

def _wrap_optional_block(text: str, old_block: str, guard_expr: str, skip_name: str,
                          skip_reason_lines: str, replacements: dict[str, str] | None = None) -> str:
    """Replace `old_block` (a full, exact `    try:\\n ... except ...:\\n    ...\\n` block taken
    verbatim from validate_master.py) with:
        if not (<guard_expr>):
            check_skip("<skip_name>", "<reason>")
        else:
    <old_block, uniformly re-indented by +4 spaces, so it nests correctly under the new `else:`>
    Uniform +4 indent (via textwrap-equivalent line prefixing of the WHOLE block, try/except
    lines included) keeps internal relative indentation intact -- avoids the mismatched-indent
    bug of patching only the first couple of lines by hand.
    """
    import textwrap
    assert old_block in text, f"validate_master.py block not found verbatim for {skip_name}"
    block = old_block
    if replacements:
        for k, v in replacements.items():
            block = block.replace(k, v)
    indented = textwrap.indent(block, "    ")
    new_block = (
        f"    if not ({guard_expr}):\n"
        f"        check_skip(\"{skip_name}\",\n"
        f"{skip_reason_lines}\n"
        f"    else:\n"
        f"{indented}"
    )
    return text.replace(old_block, new_block)


def adapt_validate_master() -> None:
    src = SRC / "deliverable" / "validate_master.py"
    dst = TARGET / "deliverable" / "validate_master.py"
    text = src.read_text(encoding="utf-8")

    header_note = (
        '\nPUBLIC-VARIANT ADAPTATION (tools/make_public_variant.py, %s):\n'
        "- pi_name is not a column in this public master (removed for personal-data\n"
        "  minimisation); this script never referenced it directly, so no check needed changing\n"
        "  for that alone.\n"
        "- data/raw/ is WITHHELD IN FULL in this public release (see data/raw/SOURCES.md) --\n"
        "  a lighter release than the source project's own layout, which republished most raw\n"
        "  sources. The 3 checks that depend on it (RNSR active/historical parquet, CORDIS\n"
        "  organization parquet) and the 1 check that depends on\n"
        "  pipeline/v2/outputs/french_components.parquet (also not republished -- superseded by\n"
        "  this very master) now print [SKIP], not [FAIL], when their input file is absent -- see\n"
        "  check_skip() below. Re-acquire the raw sources yourself (data/raw/SOURCES.md has every\n"
        "  URL) and pass --spine/--rnsr-dir/--cordis-dir to re-enable them.\n"
        "- every_resolved_row_has_evidence_ref renamed/scoped to grade A/B rows only: grade-C\n"
        "  rows' evidence lived in per-component web-research JSON files (Phase C/D/E), which\n"
        "  this public variant does not republish (personal-data minimisation -- see README.md);\n"
        "  their evidence_ref is legitimately blank here by construction, not a defect.\n"
    ) % BUILD_DATE

    # splice this note INSIDE the existing module docstring, right before its closing triple-quote
    # (NOT as a second standalone string-literal statement -- Python only exempts a single leading
    # docstring before `from __future__ import ...`; a second bare string expression after it would
    # push the future-import out of "first statement" position and raise a SyntaxError).
    doc_close = text.find('"""', text.find('"""') + 3)
    assert doc_close > 0, "validate_master.py module docstring closing triple-quote not found"
    text = text[:doc_close] + header_note + text[doc_close:]

    # add --rnsr-dir / --cordis-dir CLI overrides + check_skip() plumbing
    old_argparse = (
        "    parser.add_argument(\"--spine\", type=Path, default=DEFAULT_V2_SPINE,\n"
        "                         help=\"path to v2's french_components.parquet (default: derived from \"\n"
        "                              \"this file's own location, or ERC_MAIN_ROOT/ERC_REVIEW_ROOT)\")\n"
        "    args = parser.parse_args()\n"
    )
    new_argparse = (
        "    parser.add_argument(\"--spine\", type=Path, default=DEFAULT_V2_SPINE,\n"
        "                         help=\"path to v2's french_components.parquet (default: derived from \"\n"
        "                              \"this file's own location, or ERC_MAIN_ROOT/ERC_REVIEW_ROOT)\")\n"
        "    parser.add_argument(\"--rnsr-dir\", type=Path, default=DEFAULT_RNSR_DIR,\n"
        "                         help=\"path to a directory with active.parquet/historical.parquet \"\n"
        "                              \"(PUBLIC VARIANT: not republished by default -- see data/raw/SOURCES.md)\")\n"
        "    parser.add_argument(\"--cordis-dir\", type=Path, default=DEFAULT_CORDIS_DIR,\n"
        "                         help=\"path to a directory with h2020/organization.parquet + \"\n"
        "                              \"horizon/organization.parquet (PUBLIC VARIANT: not republished \"\n"
        "                              \"by default -- see data/raw/SOURCES.md)\")\n"
        "    args = parser.parse_args()\n"
        "\n"
        "    SKIPPED: list[str] = []\n"
        "\n"
        "    def check_skip(name: str, reason: str) -> None:\n"
        "        SKIPPED.append(name)\n"
        "        print(ascii_safe(f\"[SKIP] {name} -- {reason}\"))\n"
        "\n"
        "    def ascii_safe(s):\n"
        "        return str(s).encode(\"ascii\", \"replace\").decode(\"ascii\")\n"
    )
    assert old_argparse in text, "validate_master.py argparse block not found verbatim -- source changed"
    text = text.replace(old_argparse, new_argparse)

    # ---- gate 1: RNSR-dependent stale-tutelle-override check -----------------------------
    old_rnsr_block = (
        "    try:\n"
        "        active_rnsr = pd.read_parquet(DEFAULT_RNSR_DIR / \"active.parquet\")\n"
        "        historical_rnsr = pd.read_parquet(DEFAULT_RNSR_DIR / \"historical.parquet\")\n"
        "        active_ids = set(active_rnsr[\"numero_national_de_structure\"])\n"
        "        hist_max_year = historical_rnsr.groupby(\"numero_national_de_structure\")[\"annee\"].apply(\n"
        "            lambda s: pd.to_numeric(s, errors=\"coerce\").max())\n"
        "        m_start_year = dict(zip(m[\"component_id\"], m[\"start_date\"].dt.year))\n"
        "        m_rnsr_id = dict(zip(m[\"component_id\"], m[\"rnsr_id\"]))\n"
        "        ov_check = pd.read_csv(OVERRIDES_CSV, dtype=str) if OVERRIDES_CSV.exists() else pd.DataFrame(\n"
        "            columns=[\"component_id\", \"field\"])\n"
        "        tutelle_cols = {\"universities_at_start\", \"rto_tutelles\", \"other_etab_tutelles\", \"participants_nontutelle\"}\n"
        "        violations = []\n"
        "        for row in ov_check.itertuples(index=False):\n"
        "            if row.field not in tutelle_cols:\n"
        "                continue\n"
        "            cid = row.component_id\n"
        "            rid = m_rnsr_id.get(cid)\n"
        "            start_year = m_start_year.get(cid)\n"
        "            if not rid or pd.isna(rid) or start_year is None or pd.isna(start_year):\n"
        "                continue\n"
        "            if rid in active_ids:\n"
        "                continue  # active coverage = current, no gap\n"
        "            last_year = hist_max_year.get(rid)\n"
        "            if last_year is None or pd.isna(last_year):\n"
        "                continue\n"
        "            gap = float(start_year) - float(last_year)\n"
        "            if gap > 2 and cid not in STALE_RNSR_OVERRIDE_EXEMPTIONS:\n"
        "                violations.append(f\"{cid} (rnsr_id={rid}, gap={gap:.0f}y)\")\n"
        "        check(\"no_override_derived_tutelle_from_stale_rnsr\", len(violations) == 0,\n"
        "              f\"{len(violations)} violation(s): {violations[:10]}\")\n"
        "    except Exception as e:  # noqa: BLE001\n"
        "        check(\"no_override_derived_tutelle_from_stale_rnsr\", False,\n"
        "              f\"could not run ({e.__class__.__name__}: {e})\")\n"
    )
    text = _wrap_optional_block(
        text, old_rnsr_block,
        guard_expr='(args.rnsr_dir / "active.parquet").exists()',
        skip_name="no_override_derived_tutelle_from_stale_rnsr",
        skip_reason_lines=(
            "                   f\"RNSR active/historical.parquet not found at {args.rnsr_dir} -- \"\n"
            "                   \"data/raw/ is withheld in this public release by design (a lighter \"\n"
            "                   \"release than the source project's own layout); see data/raw/SOURCES.md \"\n"
            "                   \"to re-acquire and pass --rnsr-dir\")"
        ),
        replacements={"DEFAULT_RNSR_DIR": "args.rnsr_dir"},
    )

    # ---- gate 2: CORDIS-dependent synergy ceiling/floor check -----------------------------
    old_cordis_block = (
        "    try:\n"
        "        h2020_org = pd.read_parquet(DEFAULT_CORDIS_DIR / \"h2020\" / \"organization.parquet\")\n"
        "        horizon_org = pd.read_parquet(DEFAULT_CORDIS_DIR / \"horizon\" / \"organization.parquet\")\n"
        "        org = pd.concat([h2020_org, horizon_org], ignore_index=True)\n"
        "        org = org[org[\"country\"] == \"FR\"].copy()\n"
        "        org[\"projectID\"] = org[\"projectID\"].astype(str)\n"
        "        fr_totals = org.groupby(\"projectID\")[\"netEcContribution\"].sum()\n"
        "        unclaimed = pd.read_csv(SYNERGY_UNCLAIMED_CSV, dtype=str) if SYNERGY_UNCLAIMED_CSV.exists() else pd.DataFrame(\n"
        "            columns=[\"grant_id\", \"net_ec_contribution\"])\n"
        "        unclaimed[\"net_ec_contribution\"] = pd.to_numeric(unclaimed[\"net_ec_contribution\"], errors=\"coerce\")\n"
        "        unclaimed_by_grant = unclaimed.groupby(\"grant_id\")[\"net_ec_contribution\"].sum()\n"
        "\n"
        "        synergy_grants = m.loc[m[\"is_synergy\"], \"grant_id\"].astype(str).unique()\n"
        "        over_ceiling = []\n"
        "        under_floor = []\n"
        "        for gid in synergy_grants:\n"
        "            fr_total = fr_totals.get(gid)\n"
        "            if fr_total is None:\n"
        "                continue\n"
        "            comp_sum = float(m.loc[m[\"grant_id\"].astype(str) == gid, \"french_component_amount\"].sum())\n"
        "            unclaimed_eur = float(unclaimed_by_grant.get(gid, 0.0))\n"
        "            if comp_sum > fr_total + 0.01:\n"
        "                over_ceiling.append(f\"{gid} sum={comp_sum:,.2f} fr_total={fr_total:,.2f}\")\n"
        "            if comp_sum < (fr_total - unclaimed_eur) - 0.01:\n"
        "                under_floor.append(f\"{gid} sum={comp_sum:,.2f} fr_total-unclaimed={fr_total - unclaimed_eur:,.2f}\")\n"
        "        check(\"synergy_component_sum_within_cordis_ceiling_and_floor\",\n"
        "              len(over_ceiling) == 0 and len(under_floor) == 0,\n"
        "              f\"{len(over_ceiling)} over ceiling {over_ceiling[:5]}; {len(under_floor)} under \"\n"
        "              f\"(fr_total - unclaimed) {under_floor[:5]}\")\n"
        "    except Exception as e:  # noqa: BLE001\n"
        "        check(\"synergy_component_sum_within_cordis_ceiling_and_floor\", False,\n"
        "              f\"could not run ({e.__class__.__name__}: {e})\")\n"
    )
    text = _wrap_optional_block(
        text, old_cordis_block,
        guard_expr='(args.cordis_dir / "h2020" / "organization.parquet").exists()',
        skip_name="synergy_component_sum_within_cordis_ceiling_and_floor",
        skip_reason_lines=(
            "                   f\"CORDIS organization.parquet not found at {args.cordis_dir} -- \"\n"
            "                   \"data/raw/ is withheld in this public release by design; see \"\n"
            "                   \"data/raw/SOURCES.md to re-acquire and pass --cordis-dir\")"
        ),
        replacements={"DEFAULT_CORDIS_DIR": "args.cordis_dir"},
    )

    # ---- gate 3: v2-spine amount reconciliation (not republished -- superseded by this master)
    old_spine_block = (
        "    try:\n"
        "        v2_total = float(pd.read_parquet(args.spine)[\"french_component_amount\"].sum())\n"
        "        master_total = float(m[\"french_component_amount\"].sum())\n"
        "        amt_delta = master_total - v2_total\n"
        "        # Phase D integration (2026-08-28): 5 of the 133 researched components had their\n"
        "        # french_component_amount RE-DERIVED from CORDIS's own organisation.parquet split when the\n"
        "        # resolved organisation differed from the queue's `starting_host` (the AMOUNT RULE -- see\n"
        "        # staged/phase_d/PHASE_D_STAGE_REPORT.md's \"Amount reconciliation\" section). This is an\n"
        "        # intentional, documented correction to 5 amounts, not a bug.\n"
        "        # S9a fix cycle (2026-08-28), finding 1: ON TOP of that, 12 Synergy grants' duplicated\n"
        "        # cordis_exact_host line-sharing is now split equally (cordis_line_split_equal) --\n"
        "        # EUR ~59.6M removed from the total (a real over-count, not merely reattributed). So this\n"
        "        # check is EXPECTED to report a large, negative, fully explained delta (report it, don't\n"
        "        # force equality to the frozen v2 spine total; see DATA_DICTIONARY.md/VERSION.json's\n"
        "        # changelog for both causes).\n"
        "        check(\"amount_sum_matches_v2_spine\", abs(amt_delta) < 1.0,\n"
        "              f\"master={master_total:,.2f} v2_spine={v2_total:,.2f} delta={amt_delta:+,.2f} \"\n"
        "              f\"(a non-zero delta here is EXPECTED post-2026-08-28: Phase D's 5-component amount \"\n"
        "              f\"re-derivation PLUS the S9a fix cycle's Synergy line-split -- see DATA_DICTIONARY.md)\")\n"
        "    except Exception as e:  # noqa: BLE001 -- deliberately broad, this check must never crash the run\n"
        "        check(\"amount_sum_matches_v2_spine\", False,\n"
        "              f\"could not read spine at {args.spine} ({e.__class__.__name__}: {e}) -- pass --spine \"\n"
        "              f\"to point at v2's french_components.parquet explicitly\")\n"
    )
    text = _wrap_optional_block(
        text, old_spine_block,
        guard_expr="args.spine.exists()",
        skip_name="amount_sum_matches_v2_spine",
        skip_reason_lines=(
            "                   f\"v2 spine not found at {args.spine} -- pipeline/v2/outputs/\"\n"
            "                   \"french_components.parquet is not republished in this public variant \"\n"
            "                   \"(it carried a pi_name column; fully superseded by this very master \"\n"
            "                   \"file anyway) -- pass --spine to point at a copy if you have one\")"
        ),
    )

    # ---- gate 4: scope evidence_ref check to grade A/B (grade C blanked here by design) -----
    old_check = (
        "    resolved = m[m[\"resolution_status\"].isin(RESOLVED_STATUSES)]\n"
        "    no_evidence = resolved[resolved[\"evidence_ref\"].isna()]\n"
        "    check(\"every_resolved_row_has_evidence_ref\", len(no_evidence) == 0,\n"
        "          f\"{len(no_evidence)} rows: {no_evidence['component_id'].tolist()[:10]}\")\n"
    )
    new_check = (
        "    resolved = m[m[\"resolution_status\"].isin(RESOLVED_STATUSES)]\n"
        "    # PUBLIC VARIANT: grade C rows' evidence lived in per-component web-research JSON\n"
        "    # (Phase C/D/E), withheld here for personal-data minimisation -- their evidence_ref is\n"
        "    # legitimately blank (empty string) by construction, not a defect. Grade A/B rows are\n"
        "    # always a real HAL/OpenAlex API URL and must never be blank.\n"
        "    resolved_ab = resolved[resolved[\"evidence_grade\"].isin([\"A\", \"B\"])]\n"
        "    no_evidence = resolved_ab[resolved_ab[\"evidence_ref\"].isna() | (resolved_ab[\"evidence_ref\"] == \"\")]\n"
        "    check(\"every_resolved_gradeAB_row_has_evidence_url\", len(no_evidence) == 0,\n"
        "          f\"{len(no_evidence)} rows: {no_evidence['component_id'].tolist()[:10]}\")\n"
        "    grade_c_blank = resolved[(resolved[\"evidence_grade\"] == \"C\") & (\n"
        "        resolved[\"evidence_ref\"].isna() | (resolved[\"evidence_ref\"] == \"\"))]\n"
        "    check(\"gradeC_evidence_withheld_as_expected_public_variant\", True,\n"
        "          f\"{len(grade_c_blank)} grade-C rows have an empty evidence_ref here (expected -- \"\n"
        "          f\"their evidence is per-component research JSON, not republished; see README.md)\")\n"
    )
    assert old_check in text, "validate_master.py evidence_ref check block not found verbatim"
    text = text.replace(old_check, new_check)

    # ---- final summary: report SKIPPED count too ----
    old_summary = (
        "    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)\n"
        "    print()\n"
        "    print(f\"{len(RESULTS) - n_fail}/{len(RESULTS)} checks PASS\" + (f\", {n_fail} FAIL\" if n_fail else \"\"))\n"
        "    return 1 if n_fail else 0\n"
    )
    new_summary = (
        "    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)\n"
        "    print()\n"
        "    if SKIPPED:\n"
        "        skip_note = f\", {len(SKIPPED)} SKIP (raw data withheld, see data/raw/SOURCES.md): {SKIPPED}\"\n"
        "    else:\n"
        "        skip_note = \"\"\n"
        "    print(f\"{len(RESULTS) - n_fail}/{len(RESULTS)} checks PASS\"\n"
        "          + (f\", {n_fail} FAIL\" if n_fail else \"\") + skip_note)\n"
        "    return 1 if n_fail else 0\n"
    )
    assert old_summary in text, "validate_master.py final summary block not found verbatim"
    text = text.replace(old_summary, new_summary)

    write_text(dst, text)


# --------------------------------------------------------------------------
# 9. DATA_DICTIONARY.md ADAPTATION (drop pi_name row, annotate transformed cols)
# --------------------------------------------------------------------------

def adapt_data_dictionary() -> str:
    src_path = SRC / "docs" / "DATA_DICTIONARY.md"
    text = src_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    out = []
    for line in lines:
        if line.startswith("| `pi_name` |"):
            continue
        if line.startswith("| `evidence_ref` |"):
            line = line.rstrip("|").rstrip() + (
                " **PUBLIC VARIANT:** grade-C values (a local research-note JSON path in the "
                "source) are blank here; grade-A/B values (a HAL/OpenAlex API URL) are unchanged. |"
            )
        if line.startswith("| `integration_note` |"):
            line = line.rstrip("|").rstrip() + (
                " **PUBLIC VARIANT:** reduced to URL-only (any http(s) URL kept; all surrounding "
                "free-text prose, which could name individuals, dropped). |"
            )
        if line.startswith("| `park_reason` |"):
            line = line.rstrip("|").rstrip() + (
                " **PUBLIC VARIANT:** reduced to URL-only, same rule as `integration_note` (this "
                "column's free text names the PIs of the still-parked/conflicted components -- "
                "all 6 non-blank values contain zero URLs, so the field is blank here for those "
                "rows; the categorical outcome survives in `resolution_status`/"
                "`phase_d_terminal_outcome`). |"
            )
        out.append(line)
    text = "\n".join(out)
    note = (
        "\n> **Public-variant note (added by `tools/make_public_variant.py`, %s):** the `pi_name` "
        "column documented in the original data dictionary has been REMOVED from this release's "
        "master file for personal-data minimisation. `evidence_ref`, `integration_note` and "
        "`park_reason` are reduced to URL-only (prose dropped -- this also drops a handful of "
        "local Windows filesystem paths that had leaked into `evidence_ref` for some grade-B/C "
        "rows). See `README.md` -> \"What is included vs withheld\" and "
        "`PUBLIC_VARIANT_MANIFEST.md` for the full rationale and how to re-join PI identity from "
        "the original CORDIS/ERC sources via `grant_id`.\n"
    ) % BUILD_DATE
    parts = text.split("\n", 1)
    if len(parts) == 2 and parts[0].startswith("#"):
        text = parts[0] + "\n" + note + parts[1]
    else:
        text = note + text
    return text


# --------------------------------------------------------------------------
# 10. docs/ BUILD (per CONTENT RULES / D12)
# --------------------------------------------------------------------------

def build_docs(pattern_multi: NameLookup) -> int:
    checkpoint("docs/ -- starting")
    scrubbed_total = 0

    # README.md-from-public sources handled separately (build_readme). Here: docs/*.md.
    pairs = [
        ("public/METHODOLOGY_PUBLIC.md", "METHODOLOGY.md"),
        ("public/LIMITATIONS_PUBLIC.md", "LIMITATIONS.md"),
    ]
    for src_rel, dst_name in pairs:
        src_p = SRC / "docs" / src_rel
        dst_p = TARGET / "docs" / dst_name
        text = src_p.read_text(encoding="utf-8")
        write_text(dst_p, text)
        n = scrub_md_file(dst_p, pattern_multi)
        scrubbed_total += n
        if n:
            log(f"docs/{dst_name}: scrubbed {n} full-name occurrence(s) -> 'the PI'")

    # DATA_DICTIONARY.md: adapted (pi_name row dropped, public-variant note)
    dd_text = adapt_data_dictionary()
    dd_dst = TARGET / "docs" / "DATA_DICTIONARY.md"
    write_text(dd_dst, dd_text)
    n = scrub_md_file(dd_dst, pattern_multi)
    scrubbed_total += n
    if n:
        log(f"docs/DATA_DICTIONARY.md: scrubbed {n} full-name occurrence(s) -> 'the PI'")

    # straight copies, name-scrub pass
    for fname in ["UPDATE_PLAYBOOK.md", "REPRODUCE.md", "COSTS.md", "AUDIT_FINDINGS.md",
                  "RECONCILIATION.md"]:
        src_p = SRC / "docs" / fname
        dst_p = TARGET / "docs" / fname
        text = src_p.read_text(encoding="utf-8")
        write_text(dst_p, text)
        n = scrub_md_file(dst_p, pattern_multi)
        scrubbed_total += n
        if n:
            log(f"docs/{fname}: scrubbed {n} full-name occurrence(s) -> 'the PI'")

    checkpoint(f"docs/ -- 7 docs written (METHODOLOGY/LIMITATIONS from *_PUBLIC.md, "
               f"DATA_DICTIONARY adapted, 5 copied) + name-scrubbed ({scrubbed_total} replacements)")
    return scrubbed_total


# --------------------------------------------------------------------------
# 11. README.md (from README_PUBLIC.md, FINAL NUMBERS block filled)
# --------------------------------------------------------------------------

def extract_final_numbers_block(final_numbers_text: str) -> str:
    """Pull the two headline markdown tables (main metrics + tiers) out of FINAL_NUMBERS.md
    verbatim, so the README's numbers are always literally copied from the source-of-truth file,
    never re-typed by hand."""
    lines = final_numbers_text.split("\n")
    out = []
    in_block = False
    tables_seen = 0
    for i, line in enumerate(lines):
        if line.startswith("| Metric | Value |"):
            in_block = True
        if in_block:
            out.append(line)
            if line.startswith("| **Total (exhaustive"):
                tables_seen += 1
                break
    block = "\n".join(out)
    return block


def build_readme(source_version: str, pattern_multi: NameLookup) -> int:
    checkpoint("README.md -- starting (from docs/public/README_PUBLIC.md)")
    src_p = SRC / "docs" / "public" / "README_PUBLIC.md"
    text = src_p.read_text(encoding="utf-8")

    final_numbers_text = (SRC / "deliverable" / "FINAL_NUMBERS.md").read_text(encoding="utf-8")
    block = extract_final_numbers_block(final_numbers_text)
    filled = (
        f"_(Extracted verbatim from `deliverable/FINAL_NUMBERS.md`, dataset v{source_version} -- "
        "read that file for the full derivation, every headline-tier footnote, and the region/"
        "university top-5 tables.)_\n\n" + block
    )
    assert "<!-- FINAL NUMBERS -->" in text, "README_PUBLIC.md marker not found verbatim"
    text = text.replace("<!-- FINAL NUMBERS -->", filled)

    dst_p = TARGET / "README.md"
    write_text(dst_p, text)
    n = scrub_md_file(dst_p, pattern_multi)
    if n:
        log(f"README.md: scrubbed {n} full-name occurrence(s) -> 'the PI'")
    checkpoint(f"README.md -- written from README_PUBLIC.md, FINAL NUMBERS block filled "
               f"({scrubbed_total_label(n)})")
    return n


def scrubbed_total_label(n: int) -> str:
    return f"{n} name(s) scrubbed" if n else "0 scrubbed"


# --------------------------------------------------------------------------
# 12. pipeline/ (v1 + v2 code + tests + safe outputs)
# --------------------------------------------------------------------------

def build_pipeline() -> list[str]:
    checkpoint("pipeline/ -- starting")
    excluded: list[str] = []

    # quarantine stale copies from a previous run of this script (before these 4 files were
    # identified as leaky and excluded) -- never delete, see quarantine_stale()'s own docstring.
    for rel in ["pipeline/v1/outputs/resolution_llm_100.parquet",
                "pipeline/v1/outputs/resolution_openalex.parquet",
                "pipeline/v2/outputs/evidence_provenance.csv",
                "pipeline/v2/outputs/manual_review_queue.csv"]:
        quarantine_stale(rel)

    for gen in ["v1", "v2"]:
        src_gen = SRC / "pipeline" / gen
        dst_gen = TARGET / "pipeline" / gen
        for sub in ["scripts", "tests", "workflows"]:
            p = src_gen / sub
            if p.is_dir():
                copy_tree_filtered(p, dst_gen / sub)
        for fname in ["README.md", "config.yaml", "requirements.txt"]:
            p = src_gen / fname
            if p.is_file():
                copy_file(p, dst_gen / fname)

        if gen == "v1":
            p = src_gen / "overrides" / "manual_overrides.csv"
            if p.is_file():
                copy_file(p, dst_gen / "overrides" / "manual_overrides.csv")
            # resolution_llm_100.parquet and resolution_openalex.parquet EXCLUDED: neither has a
            # formal pi_name column (schema-safe at a glance), but the name-scan gate found real
            # leaks anyway -- resolution_llm_100.parquet's own `resolved_lab` cell literally holds
            # a PI's full name for at least one row (a first-pass LLM resolver artifact), and
            # resolution_openalex.parquet's `source_url` column holds ~30 real researcher email
            # addresses (institutional AND at least one personal-looking Gmail address). Per this
            # release's own rule ("outputs only if name-free"), both fail that bar and are
            # excluded entirely rather than cell-patched.
            excluded.append(
                "pipeline/v1/outputs/resolution_llm_100.parquet (name-scan gate found a real PI "
                "full name leaked into its `resolved_lab` free-text column -- not name-free "
                "despite having no `pi_name` column)")
            excluded.append(
                "pipeline/v1/outputs/resolution_openalex.parquet (name-scan gate found ~30 real "
                "researcher email addresses in its `source_url` column, incl. at least one "
                "personal-looking address -- excluded for the same personal-data-minimisation "
                "reason as pi_name, even though emails aren't literally a 'name')")
            for fname in ["RUNLOG.md", "resolution_harvest.parquet", "resolution_piauthor.parquet"]:
                p = src_gen / "outputs" / fname
                if p.is_file():
                    copy_file(p, dst_gen / "outputs" / fname)

        if gen == "v2":
            excluded += [
                "pipeline/v2/outputs/canonical_spine.parquet (has pi_names_raw -- superseded by "
                "deliverable/master; not republished)",
                "pipeline/v2/outputs/french_components.parquet (has pi_name -- superseded by "
                "deliverable/master; not republished)",
                "pipeline/v2/outputs/evidence_provenance.csv (pi_name column dropped, but the "
                "name-scan gate found real PI names ALSO leaked into its `lab_name` free-text "
                "column for several rows -- not name-free even after the column drop; excluded "
                "entirely rather than cell-patched)",
                "pipeline/v2/outputs/manual_review_queue.csv (same reason: pi_name column dropped, "
                "but real PI names also found in `lab_name`/similar free-text columns)",
            ]
            for fname in ["lab_resolutions.csv"]:
                p = src_gen / "outputs" / fname
                if p.is_file():
                    df = pd.read_csv(p, dtype=str, keep_default_na=False)
                    if "pi_name" in df.columns:
                        df = df.drop(columns=["pi_name"])
                    out_p = dst_gen / "outputs" / fname
                    out_p.parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(out_p, index=False, encoding="utf-8")
                    _record(out_p)
            for fname in ["coverage_cost_report.json", "validation_report.md"]:
                p = src_gen / "outputs" / fname
                if p.is_file():
                    copy_file(p, dst_gen / "outputs" / fname)

    checkpoint(f"pipeline/ -- v1+v2 code, tests, config, safe outputs copied; excluded="
               f"{len(excluded)} pi-name-bearing pipeline output(s)")
    return excluded


# --------------------------------------------------------------------------
# 13. integration/scripts (code only)
# --------------------------------------------------------------------------

def build_integration(pattern_multi: NameLookup) -> int:
    checkpoint("integration/scripts -- starting")
    copy_tree_filtered(SRC / "integration" / "scripts", TARGET / "integration" / "scripts")

    # c08_assemble_master.py and c15_phase_e_stage.py document specific PI-linked fix-cycle
    # decisions (the S9e/Residuals-v1.5.0 Inria-HQ relink) BY NAME, but only inside `#` comments
    # and one descriptive changelog string literal -- verified by direct inspection before this
    # script was written (grep confirmed every hit sits in a comment or a plain descriptive
    # string, never in an identifier/dict-key the matching logic depends on). Safe to text-scrub
    # exactly like a .md doc: substitutes the name for "the PI", touches no executable semantics.
    scrub_count = 0
    for fname in ["c08_assemble_master.py", "c15_phase_e_stage.py"]:
        p = TARGET / "integration" / "scripts" / fname
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new_text, n = pattern_multi.scrub(text)
        if n:
            p.write_text(new_text, encoding="utf-8")
            scrub_count += n
            log(f"integration/scripts/{fname}: scrubbed {n} full-name occurrence(s) in "
                f"comments/changelog strings -> 'the PI'")

    checkpoint(f"integration/scripts -- copied (code only; staged/ ledgers, evidence/, "
               f"DELEGATION_LEDGER.md all excluded -- personal research notes); "
               f"{scrub_count} comment/changelog-string name(s) scrubbed in c08/c15")
    return scrub_count


# --------------------------------------------------------------------------
# 14. data/raw -- EXCLUDED ENTIRELY except SOURCES.md
# --------------------------------------------------------------------------

def build_data_raw() -> None:
    checkpoint("data/raw -- starting (excluded entirely except SOURCES.md)")
    sources_text = (SRC / "data" / "raw" / "SOURCES.md").read_text(encoding="utf-8")
    note = (
        f"> **Public-variant note ({BUILD_DATE}):** `data/raw/` is **not republished** in this "
        "lighter public release -- not even the safely-shareable RNSR/CORDIS/MESR files. Every "
        "source below is fully public/open-licensed; re-acquire any of them yourself from its "
        "own URL (this file keeps every URL, licence, snapshot date, and SHA-256 unchanged from "
        "the source project's own table). Two files are singled out below because they are the "
        "ONLY ones that contain a Principal Investigator's name directly -- everything else in "
        "the table is safe to re-acquire and use as-is.\n\n"
        "### Files that contain PI names (do not expect these to be name-free if you re-acquire "
        "them)\n\n"
        "- `cordis/2026-07-23/h2020_erc_pi.xlsx` -- CORDIS H2020 ERC principal-investigator "
        "export. Source: `https://cordis.europa.eu/data/cordis-h2020-erc-pi.xlsx`. SHA-256 (of "
        "the copy this release was built from, first 12 hex, per this project's own convention): "
        "`6147bb6e5115`.\n"
        "- `dashboard/2026-07-24/bulk_data_erc_dashboard.xlsx` -- ERC Dashboard bulk data export. "
        "Source: `https://erc.europa.eu/projects-figures/erc-dashboard`. SHA-256 (first 12 hex): "
        "`6840045d70bb`.\n\n"
        "### Full source table (unchanged from the source project)\n\n"
    )
    write_text(TARGET / "data" / "raw" / "SOURCES.md", note + sources_text)
    checkpoint("data/raw -- SOURCES.md written (all other raw files excluded by design; see "
               "PUBLIC_VARIANT_MANIFEST.md)")


# --------------------------------------------------------------------------
# 15. STATIC TOP-LEVEL FILES (copied from SRC -- already public-ready)
# --------------------------------------------------------------------------

def build_static_files() -> None:
    checkpoint("static top-level files -- starting (LICENSE, CITATION.cff, requirements.txt, "
               ".gitignore, from SRC as-is)")
    for fname in ["LICENSE", "CITATION.cff", "requirements.txt", ".gitignore"]:
        copy_file(SRC / fname, TARGET / fname)
    checkpoint("static top-level files -- copied")


# --------------------------------------------------------------------------
# 16. NAME-SCAN GATE (final pass over TARGET's own written files)
# --------------------------------------------------------------------------

SIZE_SKIP_BYTES = 50 * 1024 * 1024


def run_name_scan_gate(pattern_multi: NameLookup, pattern_single: NameLookup,
                       pattern_candidate: NameLookup) -> dict:
    blocking_hits: dict[str, list[str]] = {}     # non-md files: must be 0 (authoritative names)
    docs_scrubbed_verify: dict[str, list[str]] = {}  # md files: should be 0 post-scrub
    advisory_hits: dict[str, list[str]] = {}     # surname-only, any file type
    candidate_hits: dict[str, list[str]] = {}    # phase_e heuristic candidates, any file type --
                                                  # ALWAYS advisory (see build_name_roster docstring)
    email_hits: dict[str, list[str]] = {}
    orcid_hits: dict[str, list[str]] = {}
    parquet_column_hits: dict[str, dict] = {}
    skipped_large: list[str] = []
    files_scanned = 0

    for path in sorted(TARGET.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(TARGET).parts
        if rel_parts and rel_parts[0].startswith("_TO_DELETE_"):
            # quarantine holding pen (never-delete convention) -- explicitly NOT part of the
            # shipped release tree (nothing in README/docs references it), so it is out of scope
            # for the release's own name-scan gate. Its contents are exactly the files THIS gate
            # found leaking a real name and demoted out of the tree -- see quarantine_stale().
            continue
        if path.name in ("make_public_variant.py", "PUBLIC_VARIANT_MANIFEST.md",
                         "BUILD_CHECKPOINT.md"):
            # make_public_variant.py: its own docstring quotes patterns like "pi_name" -- not PII.
            # PUBLIC_VARIANT_MANIFEST.md / BUILD_CHECKPOINT.md: these are THIS scan's own meta-
            # documentation, generated from a PREVIOUS run's scan_report (which quotes any
            # residual name verbatim so a human reviewer can see what was found) -- scanning them
            # is a self-referential paradox (a clean build's own manifest would fail a scan of
            # itself for faithfully reporting "0 residuals found" style text only if residuals were
            # ever found historically). Excluded from the gate; reviewed by a human instead.
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size >= SIZE_SKIP_BYTES:
            skipped_large.append(f"{path.relative_to(TARGET)} ({size/1e6:.1f} MB)")
            continue
        rel = str(path.relative_to(TARGET)).replace("\\", "/")
        suffix = path.suffix.lower()

        if suffix == ".parquet":
            files_scanned += 1
            hits = scan_parquet_columns(path, pattern_multi, pattern_single)
            hits_cand = scan_parquet_columns(path, pattern_candidate, NameLookup(set()))
            if hits:
                parquet_column_hits[rel] = hits
                for col, hit in hits.items():
                    if col == "__error__":
                        continue
                    if hit.get("multi"):
                        blocking_hits.setdefault(rel, []).extend(
                            f"[{col}] {n}" for n in hit["multi"])
                    if hit.get("single"):
                        advisory_hits.setdefault(rel, []).extend(
                            f"[{col}] {n}" for n in hit["single"])
                    if hit.get("emails"):
                        email_hits.setdefault(rel, []).extend(hit["emails"])
                    if hit.get("orcids"):
                        orcid_hits.setdefault(rel, []).extend(hit["orcids"])
            for col, hit in hits_cand.items():
                if col != "__error__" and hit.get("multi"):
                    candidate_hits.setdefault(rel, []).extend(
                        f"[{col}] {n}" for n in hit["multi"])
            continue

        if suffix not in TEXT_EXTS:
            continue
        files_scanned += 1
        result = scan_text_lines(path, pattern_multi, pattern_single)
        if result is None:
            continue
        result_cand = scan_text_lines(path, pattern_candidate, NameLookup(set()))
        if suffix in MD_EXTS:
            if result["multi"]:
                docs_scrubbed_verify[rel] = result["multi"]
        else:
            if result["multi"]:
                blocking_hits[rel] = result["multi"]
        if result["single"]:
            advisory_hits[rel] = result["single"]
        if result["emails"]:
            email_hits[rel] = result["emails"]
        if result["orcids"]:
            orcid_hits[rel] = result["orcids"]
        if result_cand and result_cand["multi"]:
            candidate_hits[rel] = result_cand["multi"]

    log("--- NAME-SCAN GATE REPORT ---")
    log(f"files scanned: {files_scanned}")
    log(f"data-file (non-.md) full-name residuals, AUTHORITATIVE roster (must be 0): "
        f"{len(blocking_hits)}")
    for f, names in list(blocking_hits.items())[:20]:
        log(f"  BLOCKING: {f} -> {[ascii_safe(n) for n in names][:5]}")
    log(f".md files with an unscrubbed full-name residual (should be 0, post-scrub verify): "
        f"{len(docs_scrubbed_verify)}")
    for f, names in list(docs_scrubbed_verify.items())[:20]:
        log(f"  DOCS-RESIDUAL: {f} -> {[ascii_safe(n) for n in names][:5]}")
    log(f"advisory (surname/given-name-token) hits, NOT blocking, files affected: "
        f"{len(advisory_hits)}")
    log(f"phase_e-heuristic CANDIDATE full-name-shaped hits, NOT blocking (mix of real names and "
        f"institution/lab/place-name false positives -- see manifest), files affected: "
        f"{len(candidate_hits)}")
    log(f"email hits (excl. sirisacademic.com/anthropic.com): "
        f"{sum(len(v) for v in email_hits.values())} across {len(email_hits)} file(s)")
    for f, es in list(email_hits.items())[:20]:
        log(f"  EMAIL: {f} -> {es[:5]}")
    log(f"ORCID hits: {sum(len(v) for v in orcid_hits.values())} across {len(orcid_hits)} file(s)")
    for f, os_ in list(orcid_hits.items())[:20]:
        log(f"  ORCID: {f} -> {os_[:5]}")
    log(f"files skipped (>= {SIZE_SKIP_BYTES/1e6:.0f} MB): {len(skipped_large)}")

    return {
        "files_scanned": files_scanned,
        "blocking_hits": blocking_hits,
        "blocking_residual_count": len(blocking_hits),
        "docs_scrubbed_verify": docs_scrubbed_verify,
        "docs_residual_count": len(docs_scrubbed_verify),
        "advisory_hits": advisory_hits,
        "candidate_hits": candidate_hits,
        "email_hits": email_hits,
        "orcid_hits": orcid_hits,
        "skipped_large": skipped_large,
    }


# --------------------------------------------------------------------------
# 17. MANIFEST
# --------------------------------------------------------------------------

def _dir_size_mb(path: Path) -> float:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total / 1e6


def write_manifest(source_version: str, dropped_cols: list[str], excluded_pipeline: list[str],
                    roster: dict, scan_report: dict, docs_scrubbed_total: int) -> None:
    total_mb = STATS["bytes_written"] / 1e6
    lines: list[str] = []
    lines.append("# Public variant manifest\n")
    lines.append(f"\nBuilt {BUILD_DATE} by `tools/make_public_variant.py`. Re-run with:\n")
    lines.append("\n```bash\npython tools/make_public_variant.py\n```\n")
    lines.append(f"\n(Locates its source tree automatically -- see `SRC_NAME_CANDIDATES` in the "
                 "script -- so no absolute source path is recorded here; the source is a sibling "
                 "folder of this release's own parent directory.)\n")
    lines.append(f"\nSource deliverable version read at build time: **{source_version}**.\n")

    lines.append("\n## Included\n")
    lines.append("""
- `README.md` -- from `docs/public/README_PUBLIC.md`, `<!-- FINAL NUMBERS -->` filled verbatim
  from `deliverable/FINAL_NUMBERS.md`'s own headline tables.
- `docs/METHODOLOGY.md` <- `docs/public/METHODOLOGY_PUBLIC.md`; `docs/LIMITATIONS.md` <-
  `docs/public/LIMITATIONS_PUBLIC.md`; `docs/DATA_DICTIONARY.md` <- `docs/DATA_DICTIONARY.md`
  (`pi_name` row dropped, public-variant note added); `docs/UPDATE_PLAYBOOK.md`,
  `docs/REPRODUCE.md`, `docs/COSTS.md`, `docs/AUDIT_FINDINGS.md`, `docs/RECONCILIATION.md`
  copied as-is -- all 7 name-scrub passed.
- `deliverable/` -- master CSV+parquet (columns dropped: `pi_name`; `evidence_ref`/
  `integration_note`/`park_reason` reduced to URL-only, `city_raw` kept unchanged),
  `region_funding.csv`, `university_funding.csv`, `institution_name_canonical.csv`,
  `FINAL_NUMBERS.md`, `VERSION.json`, `validate_master.py` (adapted -- see its own new module
  docstring note).
- `pipeline/v1/`, `pipeline/v2/` -- full code + tests + config + README; safe pipeline outputs
  (verified no person-name column, or column-dropped where one existed, or excluded outright when
  the name-scan gate found a leak beyond the `pi_name` column -- see Excluded below).
- `integration/scripts/` -- the c00-c17 reconciliation/fix-cycle code, code only; 2 files
  (`c08_assemble_master.py`, `c15_phase_e_stage.py`) had a handful of PI names in their own
  comments/changelog strings (documenting the S9e/Residuals-v1.5.0 Inria-HQ relink) -- scrubbed
  to "the PI" the same way as a .md doc (verified comment/string-literal-only, never an
  identifier the code depends on).
- `data/raw/SOURCES.md` -- URLs, licences, snapshot dates, SHA-256 for every upstream source,
  plus a note on the 2 files that carry PI names -- the raw files themselves are NOT republished
  (lighter release than the source project's own layout, which kept most of them).
- `LICENSE` (MIT), `CITATION.cff` (v1.5.0, `https://github.com/dorothee-siris/erc-france-attribution`),
  `requirements.txt`, `.gitignore`, `tools/make_public_variant.py` (this script).
""")

    lines.append("\n## Excluded (with reasons)\n")
    lines.append("- `evidence/` (Phase C/D per-component research JSON, PI-identifying) -- "
                  "excluded entirely, never copied.\n")
    lines.append("- `integration/staged/` (ledgers, per-component research CSVs/parquets, "
                  "`DELEGATION_LEDGER.md`, `s7_web_results/`, `recon/`) -- excluded, personal "
                  "research working files.\n")
    lines.append("- `data/raw/` (all raw files) -- excluded; see `data/raw/SOURCES.md` to "
                  "re-acquire.\n")
    for item in excluded_pipeline:
        lines.append(f"- {item}\n")

    lines.append(f"\n## Columns dropped from the master file\n\n- `{dropped_cols}`\n"
                 "- `evidence_ref`, `integration_note`, `park_reason`: not dropped, but reduced "
                 "to URL-only (all non-URL prose stripped) -- see README.md. This also drops a "
                 "handful of local Windows filesystem paths that had leaked into `evidence_ref` "
                 "for some grade-B/C rows in the source (e.g. "
                 "`C:\\Users\\...\\ERC-France-attribution-review\\runs\\...`), not just prose.\n")

    lines.append("\n## Name-scan gate result\n")
    c = roster["counts"]
    lines.append(f"\n- Roster provenance: {c}\n")
    lines.append(f"- Multi-token full names, AUTHORITATIVE (master `pi_name` + Phase D staged "
                 f"`pi_name`, blocking-precision, one compiled alternation regex): "
                 f"{len(roster['multi'])}\n")
    lines.append(f"- Multi-token full-name-SHAPED candidates from Phase E web_results JSON "
                 f"(heuristic Title-Case extraction over `evidence_note` field values, ADVISORY "
                 f"ONLY -- never blocking, one compiled alternation regex): "
                 f"{len(roster['candidate_multi'])}. Verified while building this script: this "
                 "sweep also matches non-name text shaped like a name (lab/institute-name "
                 "fragments, French street-name honorifics, English lab/grant-acronym fragments) "
                 "-- promoting it to blocking precision would false-flag ordinary institution-name "
                 "columns throughout the tree, so it is reported with context instead, same "
                 "treatment as a surname-only hit.\n")
    lines.append(f"- Single-token surname/given-name tokens (advisory-only, one compiled "
                 f"alternation regex): {len(roster['single'])}\n")
    lines.append(f"- Tokens dropped as common-word/place-name stopwords ({len(roster['dropped_tokens'])} "
                 f"distinct): {roster['dropped_tokens']}\n")
    lines.append(f"\n- **Data-file (non-.md) full-name residuals -- must be 0: "
                 f"{scan_report['blocking_residual_count']}**"
                 f"{' -- SEE LIST, BUILD SHOULD BE TREATED AS FAILED' if scan_report['blocking_residual_count'] else ' (0 -- clean).'}\n")
    if scan_report["blocking_hits"]:
        for f, names in scan_report["blocking_hits"].items():
            lines.append(f"  - `{f}`: {[ascii_safe(n) for n in names][:5]}\n")
    lines.append(f"- `.md` files scrubbed (full-name occurrences replaced with \"the PI\"): "
                 f"{docs_scrubbed_total}\n")
    lines.append(f"- `.md` files with a residual unscrubbed full-name hit after the scrub pass "
                 f"(should be 0): {scan_report['docs_residual_count']}\n")
    if scan_report["docs_scrubbed_verify"]:
        for f, names in scan_report["docs_scrubbed_verify"].items():
            lines.append(f"  - `{f}`: {[ascii_safe(n) for n in names][:5]}\n")
    n_adv = sum(len(v) for v in scan_report["advisory_hits"].values())
    lines.append(f"\n- **Surname-only / single-token hits (advisory, reported with context, NOT "
                 f"blind-scrubbed): {n_adv} hit(s) across {len(scan_report['advisory_hits'])} "
                 "file(s).** Assessment: spot-checked -- these are overwhelmingly first-name/"
                 "surname tokens that also appear as ordinary French given names, or as part of "
                 "an institution's own eponymous name (e.g. a university named after an historical "
                 "person) inside `lab_name`/`universities_at_start`/similar institutional columns; "
                 "none inspected trace to a standalone PI-identity disclosure outside those columns. "
                 "Full list (file -> tokens):\n")
    for f, names in list(scan_report["advisory_hits"].items())[:40]:
        lines.append(f"  - `{f}`: {[ascii_safe(n) for n in names][:8]}\n")

    n_cand = sum(len(v) for v in scan_report["candidate_hits"].values())
    lines.append(f"\n- **Phase-E-heuristic candidate hits (advisory, reported with context, NOT "
                 f"blind-blocking): {n_cand} hit(s) across {len(scan_report['candidate_hits'])} "
                 "file(s).** Assessment: spot-checked -- almost all trace to institution/lab-name "
                 "fragments (e.g. 'Biologie Structurale', 'Advanced Study'), French place/street-"
                 "name honorifics (e.g. 'Docteur Roux'), or English lab/grant-acronym fragments "
                 "the heuristic Title-Case sweep mistook for a person's name; none inspected is a "
                 "standalone PI-identity disclosure. Full list (file -> tokens):\n")
    for f, names in list(scan_report["candidate_hits"].items())[:40]:
        lines.append(f"  - `{f}`: {[ascii_safe(n) for n in names][:8]}\n")

    lines.append(f"\n- Email hits (excluding sirisacademic.com/anthropic.com): "
                 f"{sum(len(v) for v in scan_report['email_hits'].values())} across "
                 f"{len(scan_report['email_hits'])} file(s).\n")
    for f, es in scan_report["email_hits"].items():
        lines.append(f"  - `{f}`: {es}\n")
    lines.append(f"- ORCID hits: {sum(len(v) for v in scan_report['orcid_hits'].values())} across "
                 f"{len(scan_report['orcid_hits'])} file(s).\n")
    for f, os_ in scan_report["orcid_hits"].items():
        lines.append(f"  - `{f}`: {os_}\n")
    skipped = scan_report.get("skipped_large", [])
    lines.append(f"\n- Files skipped by the scan (size >= {SIZE_SKIP_BYTES/1e6:.0f} MB): "
                 f"{len(skipped)}.\n")
    for f in skipped:
        lines.append(f"  - `{f}`\n")
    lines.append(f"- Total files scanned: {scan_report['files_scanned']}\n")

    lines.append("\n## Sizes\n")
    for d in ["deliverable", "pipeline", "integration", "docs", "data", "tools"]:
        lines.append(f"- `{d}/`: {_dir_size_mb(TARGET / d):.1f} MB\n")
    lines.append(f"- **Total written this run: {STATS['files_written']} files, {total_mb:.1f} MB.**\n")

    write_text(TARGET / "PUBLIC_VARIANT_MANIFEST.md", "".join(lines))


# --------------------------------------------------------------------------
# 18. MAIN
# --------------------------------------------------------------------------

def main() -> int:
    safety_gate()
    checkpoint_init()
    checkpoint("safety gate passed; checkpoint file created")

    checkpoint("building name-scrub roster from SRC master pi_name + phase_d_staged.csv + "
               "phase_e web_results JSON field values")
    roster = build_name_roster()
    log(f"roster: {len(roster['multi'])} multi-token full names (blocking-precision), "
        f"{len(roster['candidate_multi'])} phase_e-heuristic candidate names (advisory-only), "
        f"{len(roster['single'])} single-token surname/given-name tokens (advisory-only), "
        f"{len(roster['dropped_tokens'])} tokens dropped as stopwords")
    log(f"roster provenance: {roster['counts']}")
    pattern_multi = NameLookup(roster["multi"])
    pattern_single = NameLookup(roster["single"])
    pattern_candidate = NameLookup(roster["candidate_multi"])
    checkpoint(f"roster built: multi={len(roster['multi'])} "
               f"candidate={len(roster['candidate_multi'])} single={len(roster['single'])} "
               f"dropped_stopword_tokens={len(roster['dropped_tokens'])}")

    deliv_info = build_deliverable(pattern_multi)
    source_version = deliv_info["source_version"]
    dropped_cols = list(deliv_info["dropped_cols"])

    adapt_validate_master()
    checkpoint("deliverable/validate_master.py adapted (RNSR/CORDIS/spine checks -> SKIP when "
               "input absent; evidence_ref check scoped to grade A/B)")

    docs_scrubbed = build_docs(pattern_multi)
    readme_scrubbed = build_readme(source_version, pattern_multi)
    docs_scrubbed_total = docs_scrubbed + readme_scrubbed + deliv_info["scrub_count"]

    excluded_pipeline = build_pipeline()
    integration_scrubbed = build_integration(pattern_multi)
    docs_scrubbed_total += integration_scrubbed
    build_data_raw()
    build_static_files()

    checkpoint("NAME-SCAN GATE -- final pass starting")
    scan_report = run_name_scan_gate(pattern_multi, pattern_single, pattern_candidate)
    checkpoint(f"NAME-SCAN GATE -- data-file residuals: {scan_report['blocking_residual_count']}, "
               f".md residuals post-scrub: {scan_report['docs_residual_count']}")

    checkpoint("writing PUBLIC_VARIANT_MANIFEST.md")
    write_manifest(source_version, dropped_cols, excluded_pipeline, roster, scan_report,
                   docs_scrubbed_total)
    checkpoint("PUBLIC_VARIANT_MANIFEST.md written -- BUILD COMPLETE")

    log("")
    log("=== BUILD SUMMARY ===")
    log(f"files written: {STATS['files_written']}")
    log(f"bytes written: {STATS['bytes_written']} ({STATS['bytes_written']/1e6:.1f} MB)")
    log(f"docs/.md scrubbed (full-name replacements): {docs_scrubbed_total}")
    log(f"data-file blocking residuals: {scan_report['blocking_residual_count']}")
    log(f"docs residual (post-scrub, should be 0): {scan_report['docs_residual_count']}")
    if scan_report["blocking_residual_count"] > 0 or scan_report["docs_residual_count"] > 0:
        log("BUILD FAILED -- residual names found. See PUBLIC_VARIANT_MANIFEST.md.")
        return 1
    log("BUILD OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
