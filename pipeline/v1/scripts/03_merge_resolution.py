"""Stage 3 merge: one row per grant with tier precedence + locked manual overrides."""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)
TIER_RANK = {"manual": 0, "scanr": 1, "openalex": 2, "llm-opus": 3, "llm-sonnet": 4}
COLS = ["grant_id", "resolved_lab", "rnsr_id", "tutelles", "city", "confidence", "source_tier", "source_url"]


def merge_resolutions(frames: dict, overrides: pd.DataFrame):
    parts = []
    for f in frames.values():
        if f is not None and len(f):
            parts.append(f)
    if overrides is not None and len(overrides):
        ov = overrides.copy()
        ov = ov[ov.get("locked", False).astype(bool)] if "locked" in ov.columns else ov
        if len(ov):
            ov["source_tier"] = "manual"
            ov["confidence"] = 1.0
            ov["source_url"] = ov.get("note")
            parts.append(ov)
    allrows = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in allrows.columns:
            allrows[c] = None
    allrows["_rank"] = allrows.source_tier.map(TIER_RANK).fillna(9)
    best = allrows.sort_values("_rank").drop_duplicates("grant_id", keep="first")
    return best[COLS]


def main():
    frames = {}
    for tier in ["scanr", "openalex", "llm"]:
        p = os.path.join(P["outputs"], f"resolution_{tier}.parquet")
        frames[tier] = pd.read_parquet(p) if os.path.exists(p) else None
    ov = pd.read_csv(P["overrides"]) if os.path.exists(P["overrides"]) else pd.DataFrame()
    grants = pd.read_parquet(P["spine"])[["grant_id"]]
    res = merge_resolutions(frames, ov)
    out = grants.merge(res, on="grant_id", how="left")
    out["source_tier"] = out.source_tier.fillna("unresolved")
    out.to_parquet(P["resolution"], compression="zstd", index=False)
    print(out.source_tier.value_counts().to_string())
    print(f"unresolved: {(out.source_tier == 'unresolved').sum()}/{len(out)}")
    lib_erc.runlog(cfg, f"Task 7 merge: {(out.source_tier != 'unresolved').sum()}/{len(out)} resolved")


if __name__ == "__main__":
    main()
