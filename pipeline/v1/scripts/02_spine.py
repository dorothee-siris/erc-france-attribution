"""Stage 2: build the grant spine — one row per French-hosted ERC grant.

Spine source = official French MESR dataset (fr-esr-erc-projects-entities): French list, PI, panel,
scheme (destination_code), amount (funding_project / funding_entity), both programmes, bounded on
CALL YEAR [call_year_min, call_year_max]. START YEAR is added by joining CORDIS project.csv on
project_id (both years kept). Synergy PI counts (n_fr_pis / n_total_pis) computed for the
French-portion attribution downstream.
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import pandas as pd

lib_erc.setup_stdout()
cfg = lib_erc.load_config()

SCHEME_MAP = {"STG": "Starting", "COG": "Consolidator", "ADG": "Advanced",
              "POC": "Proof of Concept", "SYG": "Synergy", "LVG": "Autre/NC"}


def map_scheme(destination_code):
    return SCHEME_MAP.get(str(destination_code).upper(), "Autre/NC")


def _latest(source, name):
    return sorted(glob.glob(os.path.join(cfg["project_root"], "data", "raw", source, "*", name)))[-1]


def load_official_spine(cfg):
    off = pd.read_json(_latest("fr_esr_erc", "records.json"))
    off["project_id"] = off["project_id"].astype(str)
    roles = cfg["host_roles"]
    picorpi = off[off.role_entity.isin(roles)].copy()

    # per-project PI counts (EU-wide) for the Synergy French-portion split
    n_total = picorpi.groupby("project_id").size().rename("n_total_pis")
    fr = picorpi[picorpi.country_code_mapping == cfg["france_country_code"]].copy()
    n_fr = fr.groupby("project_id").size().rename("n_fr_pis")
    fr["fe"] = pd.to_numeric(fr.funding_entity, errors="coerce")
    amount_fr_entity = fr.groupby("project_id").fe.sum().rename("amount_fr_entity")

    # representative French host row per grant (prefer role 'PI' over 'CO-PI')
    rep = fr.sort_values("role_entity", ascending=False).drop_duplicates("project_id", keep="first")
    rep = rep.merge(n_total, on="project_id").merge(n_fr, on="project_id").merge(amount_fr_entity, on="project_id")

    rep["scheme"] = rep.destination_code.map(map_scheme)
    rep["amount_eur"] = pd.to_numeric(rep.funding_project, errors="coerce").fillna(0.0)
    # NB: the official dataset has NO personal PI name (porteur_projet is a role flag);
    # pi_name is filled from the H2020 CORDIS ERC-PI file where available (H2020 only).
    rep = rep.rename(columns={"panel_name": "panel", "entities_name": "host_entity"})
    rep = rep[(rep.call_year >= cfg["call_year_min"]) & (rep.call_year <= cfg["call_year_max"])]
    rep = rep[rep.scheme != "Autre/NC"]  # drop the 5 LVG low-value grants
    cols = ["project_id", "acronym", "host_entity", "amount_eur", "amount_fr_entity",
            "scheme", "panel", "call_year", "n_fr_pis", "n_total_pis", "abstract"]
    out = rep[cols].copy()
    out.insert(0, "grant_id", out.project_id)
    return out


def load_h2020_pi_names(cfg):
    """H2020 ERC PI first/last names, keyed by project_id (H2020 only; HE has no open PI file)."""
    try:
        p = _latest("cordis", "h2020_erc_pi.xlsx")
    except IndexError:
        return pd.DataFrame(columns=["project_id", "pi_name"])
    pi = pd.read_excel(p, dtype=str)
    cols = {c.lower(): c for c in pi.columns}
    pid = cols.get("projectid") or cols.get("project_id")
    fn, ln = cols.get("firstname"), cols.get("lastname")
    pi["pi_name"] = (pi[fn].fillna("").str.strip() + " " + pi[ln].fillna("").str.strip()).str.strip()
    out = pi[[pid, "pi_name"]].rename(columns={pid: "project_id"})
    out["project_id"] = out.project_id.astype(str)
    return out.drop_duplicates("project_id")


def load_cordis_startdates(cfg):
    frames = []
    for name in ("project_he.csv", "project_h2020.csv"):
        try:
            p = _latest("cordis", name)
        except IndexError:
            continue
        c = pd.read_csv(p, dtype=str)
        c = c.rename(columns={"id": "project_id", "startDate": "start_date",
                              "ecMaxContribution": "cordis_amount", "masterCall": "master_call"})
        frames.append(c[[col for col in ["project_id", "start_date", "cordis_amount", "master_call"] if col in c.columns]])
    if not frames:
        return pd.DataFrame(columns=["project_id", "start_date", "cordis_amount", "master_call"])
    cd = pd.concat(frames, ignore_index=True)
    cd["project_id"] = cd.project_id.astype(str)
    return cd.drop_duplicates("project_id")


def main():
    spine = load_official_spine(cfg)
    cordis = load_cordis_startdates(cfg)
    df = spine.merge(cordis, on="project_id", how="left")
    df["start_year"] = pd.to_datetime(df.start_date, errors="coerce").dt.year
    pis = load_h2020_pi_names(cfg)
    df = df.merge(pis, on="project_id", how="left")
    df.to_parquet(lib_erc.paths(cfg)["spine"], compression="zstd", index=False)

    print(f"spine rows (FR host, call_year {cfg['call_year_min']}-{cfg['call_year_max']}): {len(df)}")
    print(f"  PI name present (H2020 file): {df.pi_name.notna().sum()}  |  start_year joined: {df.start_year.notna().sum()}")
    print("  by scheme:")
    print(df.scheme.value_counts().to_string())
    print("  by call_year:")
    print(df.call_year.value_counts().sort_index().to_string())
    lib_erc.runlog(cfg, f"Task 3 spine: {len(df)} FR grants (start_year joined {df.start_year.notna().sum()})")


if __name__ == "__main__":
    main()
