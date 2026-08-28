"""Disk-checkpointed CNRS-page harvest — resumable across sessions (WebFetch-driven, no agents).

  queue [N]            -> show the N biggest still-unresolved RTO (institution, year) groups + acronyms
  save <json> <src>    -> match extracted entries to residual by acronym, append to the checkpoint

Checkpoint = outputs/resolution_harvest.parquet (append-only; grant_id, resolved_lab, tutelles, city,
confidence, source_tier='cnrs-page', source_url). The queue is recomputed from disk each run, so a run
interrupted by the 5h session limit loses nothing already saved — the next session just continues.
extracted json = [{"acronym": "...", "resolved_lab": "...", "tutelles": ["..."], "city": "...",
                   "confidence": 0.0-1.0}]  (source_url passed as the <src> arg)
"""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)
CKPT = os.path.join(P["outputs"], "resolution_harvest.parquet")
RTO = {
    "Centre national de la recherche scientifique": "CNRS",
    "Institut national de la santé et de la recherche médicale": "INSERM",
    "Commissariat à l'énergie atomique et aux énergies alternatives": "CEA",
    "Institut national de recherche en sciences et technologies du numérique": "Inria",
    "Institut national de recherche pour l'agriculture, l'alimentation et l'environnement": "INRAE",
    "Institut de recherche pour le développement": "IRD",
    "Centre de coopération internationale en recherche agronomique pour le développement": "CIRAD",
}


def _norm(a):
    return re.sub(r"[^a-z0-9]", "", str(a).lower())


def _done_ids():
    done = set(pd.read_parquet(os.path.join(P["outputs"], "resolution_openalex.parquet")).grant_id.astype(str))
    p100 = os.path.join(P["outputs"], "resolution_llm_100.parquet")
    if os.path.exists(p100):
        r = pd.read_parquet(p100)
        done |= set(r[r.resolved_lab.notna()].grant_id.astype(str))
    if os.path.exists(CKPT):
        done |= set(pd.read_parquet(CKPT).grant_id.astype(str))
    return done


def residual_rto():
    sp = pd.read_parquet(P["spine"]).copy()
    sp["grant_id"] = sp.grant_id.astype(str)
    sp = sp[~sp.grant_id.isin(_done_ids())]
    sp["rto"] = sp.host_entity.map(RTO)
    return sp[sp.rto.notna()]


def cmd_queue(n=8):
    r = residual_rto()
    print(f"RTO residual still to resolve: {len(r)}  (checkpoint has "
          f"{len(pd.read_parquet(CKPT)) if os.path.exists(CKPT) else 0} saved)")
    g = r.groupby(["rto", "call_year"])
    order = sorted(g.size().items(), key=lambda kv: -kv[1])
    for (inst, yr), cnt in order[:n]:
        sub = r[(r.rto == inst) & (r.call_year == yr)]
        acr = ", ".join(f"{a}" for a in sub.acronym.tolist())
        print(f"\n### {inst} {yr}  ({cnt} grants)")
        print(f"    search: \"{inst} ERC {yr} laureats\" / \"ERC {yr} {inst}\"")
        print(f"    acronyms: {acr}")


def cmd_save(json_file, src):
    entries = json.load(open(json_file, encoding="utf-8"))
    r = residual_rto()
    r["k"] = r.acronym.map(_norm)
    lut = {k: gid for k, gid in zip(r.k, r.grant_id)}
    rows = []
    for e in entries:
        if not e.get("resolved_lab"):
            continue
        gid = lut.get(_norm(e.get("acronym", "")))
        if not gid:
            continue
        tut = e.get("tutelles") or []
        rows.append({"grant_id": gid, "resolved_lab": e["resolved_lab"],
                     "tutelles": ";".join(tut) if isinstance(tut, list) else str(tut),
                     "city": e.get("city"), "confidence": float(e.get("confidence", 0.8)),
                     "source_tier": "cnrs-page", "source_url": src})
    new = pd.DataFrame(rows)
    if os.path.exists(CKPT) and len(new):
        old = pd.read_parquet(CKPT)
        new = pd.concat([old, new], ignore_index=True).drop_duplicates("grant_id", keep="first")
    if len(new):
        new.to_parquet(CKPT, compression="zstd", index=False)
    print(f"matched+saved {len(rows)} grants from {len(entries)} page entries "
          f"| checkpoint total: {len(new) if len(new) else (len(pd.read_parquet(CKPT)) if os.path.exists(CKPT) else 0)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "queue"
    if cmd == "queue":
        cmd_queue(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    elif cmd == "save":
        cmd_save(sys.argv[2], sys.argv[3])
