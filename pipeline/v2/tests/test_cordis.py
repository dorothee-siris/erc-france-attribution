import pandas as pd

from cordis import normalize_organisations, select_french_participations


def test_normalize_organisations_uses_net_contribution_and_pic():
    raw = pd.DataFrame(
        [
            {
                "projectID": "101",
                "organisationID": "999",
                "name": "Université Exemple",
                "country": "FR",
                "role": "participant",
                "ecContribution": "1200.50",
                "netEcContribution": "1000.25",
                "endOfParticipation": "false",
                "active": "",
            }
        ]
    )
    result = normalize_organisations(raw)
    assert result.iloc[0].to_dict()["grant_id"] == "101"
    assert result.iloc[0].to_dict()["pic"] == "999"
    assert result.iloc[0].net_eu_contribution == 1000.25
    assert result.iloc[0].participation_ended == False


def test_select_french_participations_keeps_ended_french_host_as_transfer_evidence():
    organisations = pd.DataFrame(
        [
            {"grant_id": "1", "country": "FR", "participation_ended": True},
            {"grant_id": "2", "country": "FR", "participation_ended": False},
            {"grant_id": "3", "country": "DE", "participation_ended": False},
        ]
    )
    starts = pd.DataFrame(
        [
            {"grant_id": "1", "start_date": pd.Timestamp("2019-01-01")},
            {"grant_id": "2", "start_date": pd.Timestamp("2019-01-01")},
            {"grant_id": "3", "start_date": pd.Timestamp("2019-01-01")},
        ]
    )
    result = select_french_participations(organisations, starts)
    assert result.grant_id.tolist() == ["1", "2"]
