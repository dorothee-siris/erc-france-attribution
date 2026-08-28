import pandas as pd

from spine import build_spine


def _row(project, start, call=2015, grant_type="Starting Grants"):
    return {
        "Programme": "Horizon 2020",
        "Acronym": f"P{project}",
        "Project Title": "Title",
        "Abstract": "Abstract",
        "Researcher(s)": "Alice Example",
        "Host Institution(s)": "Example University [123,FR]",
        "Country": "France",
        "Region": "Region",
        "Project Number": project,
        "Call": "ERC-2015-STG",
        "Grant Type": grant_type,
        "Domain": "PE",
        "Panel": "PE1",
        "Call Year": call,
        "Start Date": start,
        "End Date": "2021-12-31",
        "EU contribution": 1_000_000,
        "CORDIS Link": f"https://cordis.europa.eu/project/id/{project}",
    }


def test_build_spine_filters_by_start_date_not_call_year():
    source = pd.DataFrame(
        [
            _row(1, "2016-01-01", call=2014),
            _row(2, "2026-12-31", call=2025),
            _row(3, "2015-12-31", call=2015),
            _row(4, "2027-01-01", call=2025),
        ]
    )
    result = build_spine(source, "2016-01-01", "2027-01-01")
    assert result.grant_id.tolist() == ["1", "2"]
    assert result.start_year.tolist() == [2016, 2026]


def test_build_spine_rejects_duplicate_project_ids():
    source = pd.DataFrame([_row(1, "2016-01-01"), _row(1, "2016-02-01")])
    try:
        build_spine(source, "2016-01-01", "2027-01-01")
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate grant IDs must be rejected")
