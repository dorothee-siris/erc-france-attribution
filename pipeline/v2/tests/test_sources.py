import io
import zipfile
from pathlib import Path

import pandas as pd

from sources import download_ods_parquet, extract_cordis_tables


def test_extract_cordis_tables_reads_project_and_organisation_csv():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("project.csv", '"id";"startDate"\n"1";"2019-01-01"\n')
        archive.writestr(
            "organization.csv",
            '"projectID";"organisationID";"country";"netEcContribution"\n"1";"9";"FR";"100"\n',
        )
    project, organisations = extract_cordis_tables(buffer.getvalue())
    assert project.id.astype(str).tolist() == ["1"]
    assert organisations.projectID.astype(str).tolist() == ["1"]
    assert organisations.netEcContribution.tolist() == [100]


def test_extract_cordis_tables_repairs_unescaped_semicolons_in_project_objective():
    header = [
        "id", "acronym", "status", "title", "startDate", "endDate", "totalCost",
        "ecMaxContribution", "topics", "ecSignatureDate", "frameworkProgramme", "masterCall",
        "subCall", "fundingScheme", "nature", "objective", "contentUpdateDate", "rcn",
        "grantDoi", "keywords", "Human-validated", "legalBasis",
    ]
    row = [
        "1", "A", "SIGNED", "T", "2019-01-01", "2024-01-01", "100", "100", "ERC",
        "2018-01-01", "H2020", "CALL", "SUB", "HORIZON-ERC", "", "part one", "part two",
        "2025-01-01", "9", "doi", "key", "false", "basis",
    ]
    project_text = ";".join(f'"{value}"' for value in header) + "\n" + ";".join(f'"{value}"' for value in row) + "\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("project.csv", project_text)
        archive.writestr("organization.csv", '"projectID";"organisationID";"country"\n"1";"9";"FR"\n')
    projects, _ = extract_cordis_tables(buffer.getvalue())
    assert projects.objective.tolist() == ["part one;part two"]
    assert projects.contentUpdateDate.tolist() == ["2025-01-01"]


def test_download_ods_parquet_writes_inside_root(monkeypatch, tmp_path: Path):
    payload = io.BytesIO()
    pd.DataFrame([{"id": 1}]).to_parquet(payload, index=False)

    class Response:
        content = payload.getvalue()

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("sources.requests.get", lambda *args, **kwargs: Response())
    destination = tmp_path / "v2" / "data" / "active.parquet"
    result = download_ods_parquet("dataset", destination, tmp_path / "v2")
    assert result["rows"] == 1
    assert destination.exists()
