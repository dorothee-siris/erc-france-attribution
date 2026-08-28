from __future__ import annotations

import json

import pandas as pd


def _estimated_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def prepare_batch(
    queue: pd.DataFrame,
    checkpoint: pd.DataFrame,
    max_cases: int = 10,
    max_source_characters: int = 8_000,
    estimated_token_budget: int = 40_000,
) -> tuple[pd.DataFrame, dict]:
    done = set(checkpoint.grant_id.astype(str)) if not checkpoint.empty and "grant_id" in checkpoint else set()
    candidates = queue[~queue.grant_id.astype(str).isin(done)].copy()
    rows = []
    used_tokens = 0
    stop_reason = None
    for record in candidates.itertuples(index=False):
        if len(rows) >= max_cases:
            stop_reason = "max_cases"
            break
        row = record._asdict()
        row["grant_id"] = str(row["grant_id"])
        row["evidence_text"] = str(row.get("evidence_text") or "")[:max_source_characters]
        compact = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        tokens = _estimated_tokens(compact)
        if used_tokens + tokens > estimated_token_budget:
            stop_reason = "estimated_token_budget"
            break
        row["estimated_input_tokens"] = tokens
        rows.append(row)
        used_tokens += tokens
    batch = pd.DataFrame(rows)
    ledger = {
        "case_count": len(batch),
        "estimated_tokens": used_tokens,
        "max_cases": max_cases,
        "max_source_characters": max_source_characters,
        "estimated_token_budget": estimated_token_budget,
        "hard_stop_reason": stop_reason,
        "actual_model_tokens": 0,
        "model_calls_executed": 0,
    }
    return batch, ledger
