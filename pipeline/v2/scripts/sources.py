from __future__ import annotations

import io
import csv
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from common import ensure_v2_path, sha256_file


def _read_cordis_csv(stream, filename: str) -> pd.DataFrame:
    reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""), delimiter=";", quotechar='"')
    header = next(reader)
    rows = []
    objective_index = header.index("objective") if "objective" in header else None
    trailing_after_objective = len(header) - objective_index - 1 if objective_index is not None else None
    for logical_row, row in enumerate(reader, start=2):
        if len(row) == len(header):
            rows.append(row)
            continue
        if objective_index is not None and len(row) > len(header):
            tail_start = len(row) - trailing_after_objective
            repaired = row[:objective_index] + [";".join(row[objective_index:tail_start])] + row[tail_start:]
            if len(repaired) == len(header):
                rows.append(repaired)
                continue
        raise ValueError(f"unrepairable CORDIS row width in {filename} logical row {logical_row}: {len(row)} != {len(header)}")
    frame = pd.DataFrame(rows, columns=header)
    numeric_columns = {"id", "projectID", "organisationID", "ecContribution", "netEcContribution", "totalCost", "ecMaxContribution", "rcn", "order"}
    for column in numeric_columns & set(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def extract_cordis_tables(content: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = {Path(name).name.lower(): name for name in archive.namelist()}
        project_name = names.get("project.csv")
        organisation_name = names.get("organization.csv") or names.get("organisation.csv")
        if not project_name or not organisation_name:
            raise ValueError("CORDIS ZIP does not contain project.csv and organization.csv")
        with archive.open(project_name) as stream:
            projects = _read_cordis_csv(stream, project_name)
        with archive.open(organisation_name) as stream:
            organisations = _read_cordis_csv(stream, organisation_name)
    return projects, organisations


def download_cordis_snapshot(url: str, destination: Path, root: Path, timeout: int = 600) -> dict[str, str | int]:
    target = ensure_v2_path(destination, root)
    target.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    projects, organisations = extract_cordis_tables(response.content)
    project_path = ensure_v2_path(target / "project.parquet", root)
    organisation_path = ensure_v2_path(target / "organization.parquet", root)
    projects.to_parquet(project_path, compression="zstd", index=False)
    organisations.to_parquet(organisation_path, compression="zstd", index=False)
    return {
        "url": url,
        "download_bytes": len(response.content),
        "project_rows": len(projects),
        "organisation_rows": len(organisations),
        "project_sha256": sha256_file(project_path),
        "organisation_sha256": sha256_file(organisation_path),
    }


def download_ods_records(dataset: str, destination: Path, root: Path, page_size: int = 100) -> dict[str, str | int]:
    target = ensure_v2_path(destination, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/{dataset}/records"
    rows: list[dict] = []
    offset = 0
    while True:
        response = requests.get(url, params={"limit": page_size, "offset": offset}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("results", [])
        rows.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(payload.get("total_count", offset)):
            break
        time.sleep(0.05)
    frame = pd.DataFrame(rows)
    frame.to_parquet(target, compression="zstd", index=False)
    return {"url": url, "rows": len(frame), "sha256": sha256_file(target)}


def download_ods_parquet(dataset: str, destination: Path, root: Path) -> dict[str, str | int]:
    target = ensure_v2_path(destination, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/{dataset}/exports/parquet"
    response = requests.get(url, timeout=600)
    response.raise_for_status()
    target.write_bytes(response.content)
    rows = len(pd.read_parquet(target))
    return {"url": url, "rows": rows, "sha256": sha256_file(target), "download_bytes": len(response.content)}
