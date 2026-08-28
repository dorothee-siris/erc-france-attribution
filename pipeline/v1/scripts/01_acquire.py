"""Stage 1: pull + snapshot reference data.
 - fr-esr-erc-projects-entities (SPINE: French ERC list, PI, panel, scheme, amount, both programmes)
 - RNSR (structure -> tutelles/UMR/commune/region backbone)
 - CORDIS bulk project.csv (HE + H2020), trimmed to id/startDate/ecMaxContribution/masterCall
   -> the join source for start_date (start_year), which the official dataset lacks.
LIVE — hits data.gouv / data.enseignementsup-recherche.gouv.fr / cordis.europa.eu. All free ($0)."""
import os
import sys
import io
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import requests
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()

_CORDIS_COLS = {"id", "acronym", "startDate", "ecMaxContribution", "masterCall"}


def _download(url, dest, **kw):
    r = requests.get(url, timeout=600, **kw)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    print(f"  saved {dest} ({len(r.content) // 1024} KB)")
    return dest


def _download_cordis_projects(url, dest_csv):
    """Fetch a CORDIS bulk zip, extract project.csv, keep only the columns we need for start_date."""
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = [n for n in z.namelist() if n.lower().endswith("project.csv")][0]
    with z.open(name) as fh:
        df = pd.read_csv(fh, sep=";", dtype=str, encoding="utf-8",
                         usecols=lambda c: c in _CORDIS_COLS)
    df.to_csv(dest_csv, index=False, encoding="utf-8")
    print(f"  saved {dest_csv} ({len(df)} projects)")
    return dest_csv


def acquire_all(cfg):
    out = {}
    d = lib_erc.snapshot_dir(cfg, "fr_esr_erc")
    out["fr_esr_erc"] = _download(cfg["sources"]["fr_esr_erc"], os.path.join(d, "records.json"))
    d = lib_erc.snapshot_dir(cfg, "rnsr")
    out["rnsr"] = _download(cfg["sources"]["rnsr_json"], os.path.join(d, "rnsr.json"))
    d = lib_erc.snapshot_dir(cfg, "cordis")
    out["cordis_he"] = _download_cordis_projects(cfg["sources"]["cordis_he_zip"], os.path.join(d, "project_he.csv"))
    out["cordis_h2020"] = _download_cordis_projects(cfg["sources"]["cordis_h2020_zip"], os.path.join(d, "project_h2020.csv"))
    out["cordis_h2020_erc_pi"] = _download(cfg["sources"]["cordis_h2020_erc_pi"], os.path.join(d, "h2020_erc_pi.xlsx"))
    return out


if __name__ == "__main__":
    paths = acquire_all(cfg)
    lib_erc.runlog(cfg, f"Task 2 acquire: {', '.join(paths)}")
    print("done:", paths)
