"""Prepare the residual (grants unresolved by scanR+OpenAlex) as JSON for the LLM workflow.
Offline transform (reads local parquet, writes local json). The Workflow itself is invoked separately."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()
P = lib_erc.paths(cfg)

grants = pd.read_parquet(P["spine"])
done = set()
for f in ["resolution_scanr.parquet", "resolution_openalex.parquet"]:
    p = os.path.join(cfg["project_root"], "outputs", f)
    if os.path.exists(p):
        done |= set(pd.read_parquet(p).grant_id)
residual = grants[~grants.grant_id.isin(done) & grants.pi_name.notna()]
items = residual[["grant_id", "pi_name", "acronym", "scheme", "start_year"]].to_dict("records")
open(os.path.join(cfg["project_root"], "outputs", "residual.json"), "w", encoding="utf-8").write(
    json.dumps(items, ensure_ascii=False))
print(f"residual for LLM: {len(items)} grants -> outputs/residual.json")
