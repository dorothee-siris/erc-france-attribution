"""GATE 1: does euprojectsdb hold the complete FR ERC set (both programmes, start_year>=2016)?
Compares DB counts vs the official French dataset (fr-esr-erc-projects-entities).
LIVE — hits euprojectsdb + data.enseignementsup-recherche.gouv.fr. Not run until user approves."""
import os
import sys
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc
import requests
import psycopg2
import pandas as pd
from dotenv import load_dotenv

lib_erc.setup_stdout()
load_dotenv(os.path.expanduser("~/.siris/.env"))
cfg = lib_erc.load_config()

# 1. DB: what ERC funding_scheme_ids and programmes exist, by year?
conn = psycopg2.connect(host=os.environ["EUP_HOST"], port=os.environ["EUP_PORT"],
                        dbname=os.environ["EUP_DBNAME"], user=os.environ["EUP_USER"],
                        password=os.environ["EUP_PASSWORD"], connect_timeout=30)
db = pd.read_sql("""
  select pr.funding_scheme_id, extract(year from pr.start_date)::int as start_year,
         count(distinct pr.grant_id) as n
  from eup.projects pr join eup.participations p using(grant_id)
  where p.country_code='FR'
    and (upper(pr.funding_scheme_id) like '%ERC%' or upper(pr.call_id) like '%ERC%')
  group by 1,2 order by 1,2""", conn)
conn.close()
print("== euprojectsdb FR ERC by scheme x start_year ==")
print(db.to_string())

# 2. Official dataset: FR ERC counts (country-level; the authoritative denominator)
r = requests.get(cfg["sources"]["fr_esr_erc"], timeout=120)
r.raise_for_status()
off = pd.read_json(io.BytesIO(r.content))
print("\n== fr-esr columns ==")
print(list(off.columns))
print("\n== official record count ==", len(off))

# 3. Reconciliation summary written to a decision file
lines = ["# euprojectsdb coverage probe", "",
         f"snapshot_date: {cfg['snapshot_date']}",
         f"- DB distinct FR ERC grants (start_year>=2016): {int(db[db.start_year >= 2016].n.sum())}",
         f"- official dataset total records: {len(off)}",
         "", "## DB scheme ids seen", "```", db.to_string(), "```",
         "", "## DECISION",
         "- [ ] DB reconciles within tolerance -> spine=euprojectsdb; fill config funding_scheme_ids_h2020",
         "- [ ] DB has gaps -> spine=CORDIS bulk fallback (Task 3 alt path)"]
open(os.path.join(cfg["project_root"], "outputs", "coverage_probe.md"), "w", encoding="utf-8").write("\n".join(lines))
print("\nWrote outputs/coverage_probe.md")
