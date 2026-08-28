import os
import sys
import json
import importlib
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
enrich = importlib.import_module("04_enrich")


def test_umr_flag_and_tutelles_from_rnsr(tmp_path):
    # minimal RNSR-shaped record: a UMR with two tutelles
    rec = [{"numero_national_de_structure": "200114767B", "libelle": "LPTMS",
            "code_unite": "UMR8626", "tutelles": [{"libelle": "CNRS"}, {"libelle": "Universite Paris-Saclay"}],
            "code_commune": "91471", "region": "Ile-de-France"}]
    f = tmp_path / "rnsr.json"
    f.write_text(json.dumps(rec), encoding="utf-8")
    idx = enrich.rnsr_index(str(f))
    e = idx["200114767B"]
    assert e["is_umr"] is True
    assert set(e["tutelles"]) == {"CNRS", "Universite Paris-Saclay"}


def test_commune_to_site_metropole():
    epci = pd.DataFrame([{"insee": "69123", "epci_nature": "MET", "epci_nom": "Metropole de Lyon"}])
    assert enrich.commune_to_site("69123", epci) == "Metropole de Lyon"
    assert enrich.commune_to_site("00000", epci) is None
