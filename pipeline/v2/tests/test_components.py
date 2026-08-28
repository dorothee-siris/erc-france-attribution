import pandas as pd

from components import build_components, parse_host_entries


def test_parse_host_entries_preserves_pic_and_country():
    text = (
        "National Centre for Scientific Research (CNRS) [999997930,FR], "
        "University of Porto [892061180,PT]"
    )
    assert parse_host_entries(text) == [
        {"host_name": "National Centre for Scientific Research (CNRS)", "host_pic": "999997930", "host_country": "FR"},
        {"host_name": "University of Porto", "host_pic": "892061180", "host_country": "PT"},
    ]


def test_synergy_uses_exact_french_cordis_total_and_excludes_foreign_hosts():
    spine = pd.DataFrame(
        [
            {
                "grant_id": "10",
                "acronym": "SYN",
                "pi_names_raw": "Alice France, Bob Abroad",
                "host_institutions_raw": "CNRS [111,FR], Oxford [222,UK]",
                "grant_type": "Synergy Grants",
                "project_eu_contribution": 10_000_000.0,
                "start_date": pd.Timestamp("2022-01-01"),
                "call_year": 2021,
            }
        ]
    )
    organisations = pd.DataFrame(
        [
            {"grant_id": "10", "pic": "111", "country": "FR", "net_eu_contribution": 2_500_000.0},
            {"grant_id": "10", "pic": "222", "country": "UK", "net_eu_contribution": 7_500_000.0},
        ]
    )
    result = build_components(spine, organisations)
    assert result.pi_name.tolist() == ["Alice France"]
    assert result.french_component_amount.tolist() == [2_500_000.0]
    assert result.amount_method.tolist() == ["cordis_exact_host"]


def test_synergy_falls_back_to_pi_fraction_without_cordis_amounts():
    spine = pd.DataFrame(
        [
            {
                "grant_id": "11",
                "acronym": "SYN2",
                "pi_names_raw": "Alice France, Bob Abroad",
                "host_institutions_raw": "CNRS [111,FR], Oxford [222,UK]",
                "grant_type": "Synergy Grants",
                "project_eu_contribution": 8_000_000.0,
                "start_date": pd.Timestamp("2022-01-01"),
                "call_year": 2021,
            }
        ]
    )
    result = build_components(spine, pd.DataFrame())
    assert result.french_component_amount.tolist() == [4_000_000.0]
    assert result.amount_method.tolist() == ["pi_fraction_fallback"]


def test_synergy_without_pi_names_creates_exact_french_host_components():
    spine = pd.DataFrame(
        [
            {
                "grant_id": "12", "acronym": "SYN3", "pi_names_raw": "",
                "host_institutions_raw": "FR Lab Host [111,FR], German Host [222,DE]",
                "grant_type": "Synergy Grants", "project_eu_contribution": 10_000_000.0,
                "start_date": pd.Timestamp("2022-01-01"), "call_year": 2021,
            }
        ]
    )
    organisations = pd.DataFrame(
        [{"grant_id": "12", "pic": "111", "country": "FR", "organisation_name": "FR Lab Host", "net_eu_contribution": 2_000_000.0}]
    )
    result = build_components(spine, organisations)
    assert result.pi_name.isna().all()
    assert result.starting_host.tolist() == ["FR Lab Host"]
    assert result.french_component_amount.tolist() == [2_000_000.0]
    assert result.amount_method.tolist() == ["cordis_exact_host_pi_unknown"]
