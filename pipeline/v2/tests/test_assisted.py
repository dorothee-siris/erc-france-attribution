import pandas as pd

from assisted import prepare_batch


def test_prepare_batch_caps_cases_and_source_characters_and_skips_checkpointed():
    queue = pd.DataFrame(
        [
            {"grant_id": "1", "pi_name": "A", "acronym": "A1", "starting_host": "H", "evidence_text": "x" * 100},
            {"grant_id": "2", "pi_name": "B", "acronym": "A2", "starting_host": "H", "evidence_text": "y" * 100},
            {"grant_id": "3", "pi_name": "C", "acronym": "A3", "starting_host": "H", "evidence_text": "z" * 100},
        ]
    )
    checkpoint = pd.DataFrame([{"grant_id": "1"}])
    batch, ledger = prepare_batch(queue, checkpoint, max_cases=1, max_source_characters=20, estimated_token_budget=100)
    assert batch.grant_id.tolist() == ["2"]
    assert len(batch.iloc[0].evidence_text) == 20
    assert ledger["case_count"] == 1
    assert ledger["estimated_tokens"] <= 100


def test_prepare_batch_stops_before_estimated_budget():
    queue = pd.DataFrame(
        [
            {"grant_id": "1", "pi_name": "A", "acronym": "A1", "starting_host": "H", "evidence_text": "x" * 200},
            {"grant_id": "2", "pi_name": "B", "acronym": "A2", "starting_host": "H", "evidence_text": "y" * 200},
        ]
    )
    batch, ledger = prepare_batch(queue, pd.DataFrame(), max_cases=10, max_source_characters=200, estimated_token_budget=100)
    assert len(batch) == 1
    assert ledger["hard_stop_reason"] == "estimated_token_budget"
