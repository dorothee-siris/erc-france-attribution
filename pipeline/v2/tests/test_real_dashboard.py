from pathlib import Path

import pandas as pd

from spine import build_spine


def test_real_dashboard_start_cohort_has_expected_shape():
    workbook = Path(__file__).resolve().parents[2] / "bulk_data_erc_dashboard.xlsx"
    source = pd.read_excel(workbook)
    result = build_spine(source, "2016-01-01", "2027-01-01")
    assert len(result) == 1414
    assert result.grant_id.nunique() == 1414
    assert result.is_synergy.sum() == 42
    assert (~result.is_synergy).sum() == 1372
    assert ((result.call_year < 2016) & (result.start_year >= 2016)).sum() == 120
