import pandas as pd

from rnsr import enrich_from_rnsr


def test_rnsr_uses_start_year_record_and_explicit_region():
    resolutions = pd.DataFrame([{"component_id": "1:0", "rnsr_id": "200012345A", "start_year": 2019}])
    history = pd.DataFrame(
        [
            {"rnsr_id": "200012345A", "year": 2018, "lab_name": "Old", "tutelles": ["CNRS"], "commune_code": "75056", "region": "Île-de-France", "unit_type": "UMR"},
            {"rnsr_id": "200012345A", "year": 2019, "lab_name": "At start", "tutelles": ["CNRS", "Université X"], "commune_code": "34172", "region": "Occitanie", "unit_type": "UMR"},
        ]
    )
    result = enrich_from_rnsr(resolutions, history)
    assert result.iloc[0].lab_name == "At start"
    assert result.iloc[0].region == "Occitanie"
    assert result.iloc[0].tutelles == ["CNRS", "Université X"]
