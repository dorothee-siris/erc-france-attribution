"""Aggregate validation + plausibility gates for the attribution outputs. Deterministic, no network,
no model. Turns "78% resolved" into a set of PASS/WARN/FAIL checks that would have caught the
region-attribution bugs found in the 2026-07-28 stress test (Institut Pasteur -> Guadeloupe;
Saint-Denis -> La Réunion; duplicate PACA region rows).

Writes outputs/validation_report.md (+ .json). Run after 05_merge_enrich_attribute.py.

Checks:
  1. Fractional reconciliation   — Σ region fractional € == Σ resolved component € (within tolerance).
  2. Canonical regions           — no two region rows collapse to the same canonical key (dup guard).
  3. Overseas plausibility       — DOM/COM regions above a small threshold are flagged for review
                                    (metropolitan France holds essentially all ERC hosts).
  4. Bare-institution linkage    — resolved labs that are just a parent-institution name should NOT
                                    carry an RNSR id (that is the fuzzy-match false-precision bug).
  5. Region coverage             — share of resolved components with an unknown region.
  6. External anchors (optional) — if validation/published_anchors.csv exists, compare our per-host
                                    ERC grant counts against published figures the user supplied.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252; report contains non-ASCII
except Exception:
    pass
sys.path.insert(0, __file__.rsplit("scripts", 1)[0] + "scripts")
from common import V2_ROOT, ensure_v2_path  # noqa: E402
from region import region_key  # noqa: E402

OUT = V2_ROOT / "outputs"
DOM_REGIONS = {"Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte"}
DOM_GRANT_WARN = 3          # more than this many grants in one DOM region is implausible for ERC
GENERIC_INSTITUTIONS = {    # bare parent bodies that are not themselves a performing unit
    "institut pasteur", "institut curie", "college de france", "inserm", "cnrs", "cea", "inria",
    "institut national de la sante et de la recherche medicale",
    "centre national de la recherche scientifique",
}


def _norm(v):
    import unicodedata
    a = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(a.replace(";", " ").split())


def main():
    comp = pd.read_parquet(ensure_v2_path(OUT / "french_components.parquet"))
    resolved = comp[comp.review_status == "auto_accepted"].copy()
    region = pd.read_csv(ensure_v2_path(OUT / "region_funding.csv"))
    checks, status = [], {"PASS": 0, "WARN": 0, "FAIL": 0}

    def add(name, ok, detail, hard=True):
        verdict = "PASS" if ok else ("FAIL" if hard else "WARN")
        status[verdict] += 1
        checks.append((verdict, name, detail))

    # 1. fractional reconciliation
    comp_total = float(pd.to_numeric(resolved.french_component_amount).sum())
    reg_total = float(pd.to_numeric(region.eur_fractional).sum())
    add("fractional_reconciles",
        abs(comp_total - reg_total) < max(1.0, 1e-6 * comp_total),
        f"Σ region fractional €{reg_total:,.0f} vs Σ component €{comp_total:,.0f}")

    # 2. no duplicate canonical regions
    keys = region.region.dropna().map(region_key)
    dups = keys[keys.duplicated(keep=False)]
    dup_names = sorted(set(region.region.dropna()[dups.index])) if len(dups) else []
    add("regions_canonical", not dup_names, f"duplicate canonical region rows: {dup_names or 'none'}")

    # 3. overseas plausibility
    dom = region[region.region.isin(DOM_REGIONS)]
    flagged = dom[dom.grants > DOM_GRANT_WARN][["region", "grants", "eur_fractional"]]
    add("overseas_plausible", flagged.empty,
        ("ok" if flagged.empty else
         "; ".join(f"{r.region}: {int(r.grants)} grants €{r.eur_fractional:,.0f}" for r in flagged.itertuples())),
        hard=False)

    # 4. bare-institution names must not carry an RNSR id
    bad = resolved[resolved.rnsr_id.notna() & resolved.lab_name.map(_norm).isin(GENERIC_INSTITUTIONS)]
    add("no_bare_institution_rnsr_link", bad.empty,
        ("ok" if bad.empty else
         f"{len(bad)} bare-institution labs carry an rnsr_id: "
         + ", ".join(sorted(set(bad.lab_name.astype(str)))[:5])),
        hard=False)

    # 5. region coverage
    unknown = int(resolved.region.isna().sum())
    add("region_coverage", True,
        f"{len(resolved) - unknown}/{len(resolved)} resolved components have a region "
        f"({unknown} unknown, {100*unknown/max(len(resolved),1):.0f}%)", hard=False)

    # 6. optional external anchors
    anchor_path = V2_ROOT / "validation" / "published_anchors.csv"
    if anchor_path.exists():
        anchors = pd.read_csv(anchor_path)  # cols: host_norm, published_count, source_url
        host_counts = (resolved.assign(h=resolved.starting_host.map(_norm))
                       .groupby("h").grant_id.nunique())
        lines = []
        for a in anchors.itertuples():
            got = int(host_counts.get(_norm(a.host_norm), 0))
            pub = int(a.published_count)
            ok = pub == 0 or abs(got - pub) / pub <= 0.15
            lines.append(f"{'ok' if ok else 'DRIFT'} {a.host_norm}: ours={got} published={pub}")
        add("external_anchors", all(l.startswith("ok") for l in lines), " | ".join(lines), hard=False)
    else:
        checks.append(("SKIP", "external_anchors",
                       "no validation/published_anchors.csv — add published per-host ERC counts "
                       "(cols: host_norm,published_count,source_url) to enable this ground-truth check"))

    # report
    md = ["# Attribution validation report", "",
          f"resolved components: {len(resolved)} | PASS {status['PASS']} · WARN {status['WARN']} · FAIL {status['FAIL']}",
          "", "| verdict | check | detail |", "|---|---|---|"]
    for v, n, d in checks:
        md.append(f"| {v} | {n} | {d} |")
    ensure_v2_path(OUT / "validation_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    ensure_v2_path(OUT / "validation_report.json").write_text(
        json.dumps({"summary": status, "checks": [{"verdict": v, "check": n, "detail": d} for v, n, d in checks]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(f"{v:5} {n}: {d}" for v, n, d in checks))
    print(f"\nPASS {status['PASS']} · WARN {status['WARN']} · FAIL {status['FAIL']}")
    if status["FAIL"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
