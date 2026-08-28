from __future__ import annotations

import argparse
import json

import pandas as pd

from assisted import prepare_batch
from common import V2_ROOT, ensure_v2_path, load_config


parser = argparse.ArgumentParser(description="Prepare a cost-capped evidence adjudication batch; does not call a model.")
parser.add_argument("--max-cases", type=int)
parser.add_argument("--max-searches-per-case", type=int)
parser.add_argument("--max-source-characters", type=int)
parser.add_argument("--estimated-token-budget", type=int)
args = parser.parse_args()
cfg = load_config()["assisted"]

queue_path = ensure_v2_path(V2_ROOT / "outputs" / "manual_review_queue.csv")
queue = pd.read_csv(queue_path, dtype={"grant_id": str})
candidate_frames = []
for name in ("hal_candidates", "openalex_candidates"):
    path = ensure_v2_path(V2_ROOT / "checkpoints" / f"{name}.parquet")
    if path.exists():
        candidate_frames.append(pd.read_parquet(path))
candidates = pd.concat(candidate_frames, ignore_index=True) if candidate_frames else pd.DataFrame()
if not candidates.empty:
    candidates["evidence_piece"] = candidates.apply(
        lambda row: f"{row.get('source_kind')}: {row.get('lab_name')} | {row.get('source_url')}", axis=1
    )
    evidence = candidates.groupby("component_id").evidence_piece.apply(lambda values: "\n".join(dict.fromkeys(values))).rename("evidence_text")
    queue = queue.merge(evidence, on="component_id", how="left")
else:
    queue["evidence_text"] = ""

checkpoint_path = ensure_v2_path(V2_ROOT / "checkpoints" / "assisted_resolutions.csv")
checkpoint = pd.read_csv(checkpoint_path, dtype={"grant_id": str}) if checkpoint_path.exists() else pd.DataFrame()
batch, ledger = prepare_batch(
    queue,
    checkpoint,
    max_cases=args.max_cases or cfg["low_effort_max_cases"],
    max_source_characters=args.max_source_characters or cfg["max_source_characters"],
    estimated_token_budget=args.estimated_token_budget or cfg["hard_tokens"],
)
ledger["max_searches_per_case"] = args.max_searches_per_case or cfg["max_searches_per_case"]
ledger["model"] = "not_executed"
ledger["effort"] = "low_recommended"
ledger["parallel_agents"] = 0

batch_path = ensure_v2_path(V2_ROOT / "checkpoints" / "assisted_batch.json")
batch_path.write_text(json.dumps(batch.to_dict("records"), ensure_ascii=False, indent=2), encoding="utf-8")
ledger_path = ensure_v2_path(V2_ROOT / "outputs" / "cost_ledger.json")
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
pd.DataFrame([ledger]).to_csv(ensure_v2_path(V2_ROOT / "outputs" / "cost_ledger.csv"), index=False, encoding="utf-8")
print(json.dumps(ledger, ensure_ascii=False, indent=2))
print("No model or agent was called. Review checkpoints/assisted_batch.json before any assisted run.")
