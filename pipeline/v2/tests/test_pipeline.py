from pathlib import Path

import pandas as pd

from pipeline import build_local_outputs


def test_build_local_outputs_writes_only_under_requested_v2_root(tmp_path: Path):
    dashboard = pd.DataFrame(
        [
            {
                "Programme": "Horizon 2020",
                "Acronym": "TEST",
                "Project Title": "Title",
                "Abstract": "Abstract",
                "Researcher(s)": "Alice Example",
                "Host Institution(s)": "Example University [123,FR]",
                "Country": "France",
                "Region": "Region",
                "Project Number": 1,
                "Call": "ERC-2015-STG",
                "Grant Type": "Starting Grants",
                "Domain": "PE",
                "Panel": "PE1",
                "Call Year": 2015,
                "Start Date": "2016-01-01",
                "End Date": "2021-01-01",
                "EU contribution": 1_000_000,
                "CORDIS Link": "https://cordis.europa.eu/project/id/1",
            }
        ]
    )
    result = build_local_outputs(dashboard, pd.DataFrame(), tmp_path / "v2", "2016-01-01", "2027-01-01")
    assert result["spine_rows"] == 1
    assert (tmp_path / "v2" / "outputs" / "canonical_spine.parquet").exists()
    assert not (tmp_path / "outputs").exists()
