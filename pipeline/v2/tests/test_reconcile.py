import pandas as pd

from reconcile import reconcile_dashboard_cordis


def test_reconcile_adds_synergy_french_component_coordinator_and_confirmed_transfer_only():
    dashboard = pd.DataFrame(
        [
            {
                "grant_id": "1", "programme": "Horizon Europe", "acronym": "DASH", "project_title": "T",
                "abstract": "", "pi_names_raw": "Alice", "host_institutions_raw": "FR Host [1,FR]",
                "dashboard_country": "France", "dashboard_region": None, "grant_type": "Starting Grants",
                "domain": None, "panel": None, "call": "ERC-2021-STG", "call_year": 2021,
                "start_date": pd.Timestamp("2022-01-01"), "start_year": 2022, "end_date": pd.Timestamp("2027-01-01"),
                "project_eu_contribution": 1_000_000.0, "cordis_url": "u", "is_synergy": False,
            }
        ]
    )
    projects = pd.DataFrame(
        [
            {"id": 2, "acronym": "SYG", "title": "S", "startDate": "2022-01-01", "endDate": "2028-01-01", "ecMaxContribution": 10_000_000, "masterCall": "ERC-2021-SYG", "fundingScheme": "HORIZON-ERC-SYG", "frameworkProgramme": "HORIZON", "objective": ""},
            {"id": 3, "acronym": "COORD", "title": "C", "startDate": "2022-01-01", "endDate": "2027-01-01", "ecMaxContribution": 2_000_000, "masterCall": "ERC-2021-COG", "fundingScheme": "HORIZON-ERC", "frameworkProgramme": "HORIZON", "objective": ""},
            {"id": 4, "acronym": "THIRD", "title": "X", "startDate": "2022-01-01", "endDate": "2027-01-01", "ecMaxContribution": 2_000_000, "masterCall": "ERC-2021-COG", "fundingScheme": "HORIZON-ERC", "frameworkProgramme": "HORIZON", "objective": ""},
            {"id": 5, "acronym": "MOVE", "title": "M", "startDate": "2022-01-01", "endDate": "2027-01-01", "ecMaxContribution": 2_000_000, "masterCall": "ERC-2021-COG", "fundingScheme": "HORIZON-ERC", "frameworkProgramme": "HORIZON", "objective": ""},
        ]
    )
    organisations = pd.DataFrame(
        [
            {"grant_id": "2", "pic": "20", "organisation_name": "FR Synergy", "country": "FR", "role": "participant", "net_eu_contribution": 2_000_000},
            {"grant_id": "2", "pic": "21", "organisation_name": "DE Synergy", "country": "DE", "role": "coordinator", "net_eu_contribution": 8_000_000},
            {"grant_id": "3", "pic": "30", "organisation_name": "FR Coordinator", "country": "FR", "role": "coordinator", "net_eu_contribution": 2_000_000},
            {"grant_id": "4", "pic": "40", "organisation_name": "FR Third", "country": "FR", "role": "thirdParty", "net_eu_contribution": 100_000},
            {"grant_id": "5", "pic": "50", "organisation_name": "FR Former", "country": "FR", "role": "participant", "net_eu_contribution": 2_000_000},
        ]
    )
    v1 = pd.DataFrame([{"grant_id": "5", "pi_name": "Moved PI", "call_year": 2021, "scheme": "Consolidator", "panel": "PE1", "host_entity": "FR Former"}])
    result, audit = reconcile_dashboard_cordis(dashboard, projects, organisations, v1, "2016-01-01", "2027-01-01")
    assert set(result.grant_id) == {"1", "2", "3", "5"}
    assert set(audit[audit.included].inclusion_reason) == {"dashboard", "cordis_synergy_fr_component", "cordis_fr_coordinator", "v1_confirmed_transfer"}


def test_reconcile_excludes_non_erc_funding_scheme_even_when_call_contains_erc():
    projects = pd.DataFrame([{"id": 9, "acronym": "NCP", "title": "N", "startDate": "2025-01-01", "endDate": "2026-01-01", "ecMaxContribution": 1, "masterCall": "HORIZON-ERC-2025-NCPS-IBA", "fundingScheme": "HORIZON-CSA", "frameworkProgramme": "HORIZON", "objective": ""}])
    organisations = pd.DataFrame([{"grant_id": "9", "pic": "90", "organisation_name": "FR", "country": "FR", "role": "coordinator", "net_eu_contribution": 1}])
    result, _ = reconcile_dashboard_cordis(pd.DataFrame(), projects, organisations, pd.DataFrame(), "2016-01-01", "2027-01-01")
    assert result.empty
