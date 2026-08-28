import pandas as pd

from compare import compare_perimeters


def test_compare_perimeters_labels_added_removed_and_common():
    v1 = pd.DataFrame([{"grant_id": "1"}, {"grant_id": "2"}])
    v2 = pd.DataFrame([{"grant_id": "2"}, {"grant_id": "3"}])
    result = compare_perimeters(v1, v2).set_index("grant_id")
    assert result.loc["1", "perimeter_status"] == "v1_only"
    assert result.loc["2", "perimeter_status"] == "both"
    assert result.loc["3", "perimeter_status"] == "v2_only"
