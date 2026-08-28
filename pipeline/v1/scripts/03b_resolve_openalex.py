"""Stage 3 primary resolver: grant-ID -> host lab via OpenAlex.

Route (validated 2026-07-23): works filtered by `awards.funder_award_id:<grant_id>` carry
raw_affiliation_strings that name the real UMR + cotutelles even when the CORDIS host is CNRS.
- PI name known (H2020): isolate the PI's own authorship by last-name match -> their French lab.
- PI name unknown (HE): aggregate the most frequent French lab across all authorships.
Recent grants (no publications yet) return 0 works -> left for the LLM tier.

LIVE — OpenAlex (key). ~1 call/grant. Respect the ~$1/day budget: stop + warn on Retry-After stalls.
"""
import os
import sys
import re
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import requests
import pandas as pd
from dotenv import load_dotenv

lib_erc.setup_stdout()
load_dotenv(os.path.expanduser("~/.siris/.env"))
cfg = lib_erc.load_config()
MAILTO = os.environ.get("OPENALEX_MAILTO")
KEY = os.environ.get("OPENALEX_API_KEY")
UMR_RE = re.compile(r"\b(U[MA]R\s?_?S?\s?\d{3,4}|UMS\s?\d{3,4})\b", re.I)
LAB_KW = ("laboratoire", "institut", "centre", "unité", "unite", "umr", "uar", "ums", " lab")
# national RTOs: a bare RTO name means the HQ effect was NOT defeated -> not a real resolution
RTO_ONLY = ("centre national de la recherche scientifique", "cnrs",
            "institut national de la sante et de la recherche medicale", "inserm",
            "commissariat a l'energie atomique", "cea", "inria",
            "institut national de recherche en sciences et technologies", "inrae",
            "institut national de recherche pour l'agriculture")


def _norm(s):
    return re.sub(r"[^a-z ]", "", str(s).lower()).strip()


def _is_rto_only(lab):
    n = _norm(lab)
    return any(n == _norm(r) or n.startswith(_norm(r)) for r in RTO_ONLY) or len(n) < 4


def _has_lab_kw(s):
    return bool(UMR_RE.search(s)) or any(k in s.lower() for k in LAB_KW)


def _get(url, params):
    p = dict(params, mailto=MAILTO)
    if KEY:
        p["api_key"] = KEY
    for attempt in range(4):
        r = requests.get(url, params=p, timeout=40)
        if r.status_code == 429 or (r.status_code == 403 and "Retry-After" in r.headers):
            raise RuntimeError(f"OpenAlex throttled/budget (HTTP {r.status_code}, Retry-After="
                               f"{r.headers.get('Retry-After')}). STOPPING — check $1/day budget.")
        if r.status_code == 200:
            return r.json()
        time.sleep(1.5 * (attempt + 1))
    return {}


def _extract_lab(raw):
    """From a French affiliation string, return the lab-bearing segment (prefer UMR/lab-keyword part)."""
    parts = [p.strip() for p in str(raw).split(",")]
    for p in parts:
        if _has_lab_kw(p) and not _is_rto_only(p):
            return p
    for p in parts:  # else a non-RTO named institution
        if p and not _is_rto_only(p) and "france" not in p.lower() and not p.strip().isdigit():
            return p
    return parts[0] if parts else str(raw)


def openalex_grant_lab(grant_id, pi_name=None):
    j = _get("https://api.openalex.org/works",
             {"filter": f"awards.funder_award_id:{grant_id}", "per_page": 50,
              "select": "id,publication_year,authorships"})
    works = j.get("results", [])
    if not works:
        return None
    pi_last = str(pi_name).split()[-1].lower() if pi_name and str(pi_name).strip() else None
    lab_strings, other_strings, inst_names = Counter(), Counter(), Counter()
    pi_matched = False
    for w in works:
        for a in w.get("authorships", []):
            name = (a.get("author") or {}).get("display_name", "") or ""
            insts = a.get("institutions", []) or []
            fr_inst = [i for i in insts if i.get("country_code") == "FR"]
            strings = a.get("raw_affiliation_strings", []) or []
            fr_string = any("france" in s.lower() for s in strings)
            is_fr = bool(fr_inst) or fr_string
            is_pi = pi_last is not None and pi_last in name.lower()
            if is_pi and is_fr:
                pi_matched = True
            # HARD FRENCH GATE: use PI's own French affiliations if PI known+French, else any French author
            use = (is_pi and is_fr) if pi_last else is_fr
            if not use:
                continue
            for s in strings:
                # only keep strings that are actually French (kills foreign co-author leaks)
                if "france" not in s.lower() and not fr_inst:
                    continue
                if _has_lab_kw(s):
                    lab_strings[s.strip()] += 1
                else:
                    other_strings[s.strip()] += 1
            for i in fr_inst:
                if i.get("display_name"):
                    inst_names[i["display_name"]] += 1
    # prefer a lab-keyword French string; else a non-RTO institution; else give up (-> next tier)
    best_raw, conf_base = "", 0.0
    if lab_strings:
        best_raw, conf_base = lab_strings.most_common(1)[0][0], 0.7
    lab = _extract_lab(best_raw) if best_raw else None
    if not lab or _is_rto_only(lab):
        non_rto = [n for n, _ in inst_names.most_common() if not _is_rto_only(n)]
        if non_rto:  # a university/named institution (no lab granularity) — weaker but usable
            lab, best_raw, conf_base = non_rto[0], best_raw or non_rto[0], 0.45
        else:
            return None  # only RTO/foreign found -> HQ effect not defeated, leave for LLM
    m = UMR_RE.search(best_raw)
    tutelles = [n for n, _ in inst_names.most_common(4)]
    conf = min(0.85, conf_base + (0.1 if pi_matched else 0.0))
    return {"resolved_lab": lab, "resolved_lab_raw": best_raw,
            "umr_code": m.group(0).upper().replace(" ", "") if m else None,
            "rnsr_id": None, "tutelles": ";".join(tutelles) if tutelles else None,
            "city": None, "confidence": round(conf, 2), "source_tier": "openalex",
            "source_url": f"https://api.openalex.org/works?filter=awards.funder_award_id:{grant_id}",
            "pi_matched": pi_matched, "n_works": len(works)}


def resolve(grants, out_path, sleep=0.15):
    rows = []
    for i, (_, g) in enumerate(grants.iterrows(), 1):
        try:
            hit = openalex_grant_lab(g.grant_id, g.get("pi_name"))
        except RuntimeError as e:
            print(f"[{i}] {e}")
            break
        if hit:
            rows.append({"grant_id": g.grant_id, **hit})
        if i % 25 == 0:
            print(f"  {i}/{len(grants)} processed, {len(rows)} resolved")
        time.sleep(sleep)
    out = pd.DataFrame(rows)
    out.to_parquet(out_path, compression="zstd", index=False)
    return out


def main():
    grants = pd.read_parquet(lib_erc.paths(cfg)["spine"])
    print(f"OpenAlex deterministic pass over {len(grants)} grants (~{len(grants)} calls)")
    out = resolve(grants, os.path.join(cfg["project_root"], "outputs", "resolution_openalex.parquet"))
    print(f"OpenAlex resolved {len(out)}/{len(grants)}")
    lib_erc.runlog(cfg, f"Task 5 OpenAlex resolved {len(out)}/{len(grants)}")


if __name__ == "__main__":
    main()
