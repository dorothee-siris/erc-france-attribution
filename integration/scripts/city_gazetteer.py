"""S9c fix cycle, finding H: a small commune -> region gazetteer, for the ONE narrow case where the
master's own region-derivation chain left `region` null even though `city` is a clean, unambiguous
French commune name (hostile review F10 class; named example 101020459:0, Meudon).

No such gazetteer existed anywhere in this project before this fix -- built fresh, deliberately
small and EXACT-MATCH ONLY (never substring/contains), because most of the 223 no-region resolved
rows carry a `city` value that is NOT a clean commune name at all (a full street address, a foreign
city -- Princeton NJ, Tokyo, Prague, Boston MA, Berkeley CA -- or None): a substring match would
wrongly fire on any of those (e.g. matching "Paris" inside "24 rue Lhomond 75231 PARIS Cedex 05" is
fine, but matching "Boston" inside a Massachusetts address must never produce a French region).
Exact-match on the normalized (accent/case-folded) city string is the safe, conservative rule the
task asks for ("unambiguous").

Coverage: the communes actually observed as CLEAN (non-address, non-foreign) values among this
run's own no-region rows, plus a modest set of other major French cities for robustness on any
future re-run with different rows. NOT exhaustive -- extend by adding more (commune_key, region)
entries below if a future run finds another clean-but-unmatched city.
"""
from __future__ import annotations

import re
import unicodedata


def _key(s: str) -> str:
    s2 = unicodedata.normalize("NFKD", str(s))
    s2 = "".join(c for c in s2 if not unicodedata.combining(c))
    s2 = re.sub(r"[^a-z0-9]+", "", s2.lower())
    return s2


# commune (as it would read, accents stripped by _key at lookup time) -> canonical region name
# (spelled exactly as region.py's _CANON_NAMES, so canon_region() is a no-op on these values).
_CITY_REGION = {
    "Meudon": "Île-de-France",
    "Paris": "Île-de-France",
    "Versailles": "Île-de-France",
    "Villejuif": "Île-de-France",
    "Toulouse": "Occitanie",
    "Montpellier": "Occitanie",
    "Nimes": "Occitanie",
    "Perpignan": "Occitanie",
    "Strasbourg": "Grand Est",
    "Nancy": "Grand Est",
    "Reims": "Grand Est",
    "Metz": "Grand Est",
    "Lyon": "Auvergne-Rhône-Alpes",
    "Grenoble": "Auvergne-Rhône-Alpes",
    "Clermont-Ferrand": "Auvergne-Rhône-Alpes",
    "Saint-Etienne": "Auvergne-Rhône-Alpes",
    "Marseille": "Provence-Alpes-Côte d'Azur",
    "Nice": "Provence-Alpes-Côte d'Azur",
    "Avignon": "Provence-Alpes-Côte d'Azur",
    "Toulon": "Provence-Alpes-Côte d'Azur",
    "Bordeaux": "Nouvelle-Aquitaine",
    "Pau": "Nouvelle-Aquitaine",
    "Limoges": "Nouvelle-Aquitaine",
    "Poitiers": "Nouvelle-Aquitaine",
    "Rennes": "Bretagne",
    "Brest": "Bretagne",
    "Nantes": "Pays de la Loire",
    "Angers": "Pays de la Loire",
    "Le Mans": "Pays de la Loire",
    "Lille": "Hauts-de-France",
    "Amiens": "Hauts-de-France",
    "Caen": "Normandie",
    "Rouen": "Normandie",
    "Dijon": "Bourgogne-Franche-Comté",
    "Besancon": "Bourgogne-Franche-Comté",
    "Orleans": "Centre-Val de Loire",
    "Tours": "Centre-Val de Loire",
    # Residuals v1.5.0 (STEP 1, city_unnormalized gazetteer extension): well-known research-hub
    # communes needed to safely resolve the mid-string-postal-code class of city_unnormalized rows
    # in c08_assemble_master.py's fix_city_hygiene_v131 residual pass. Hand-vetted, no web access --
    # these are unambiguous, well-documented commune/region pairs (Orsay/Fontainebleau = Essonne/
    # Seine-et-Marne, both Île-de-France; Villeneuve-d'Ascq = Nord, Hauts-de-France; Saint-Denis here
    # is the Seine-Saint-Denis (93) commune, Île-de-France -- NOT La Réunion's capital of the same
    # name; Sophia Antipolis = Alpes-Maritimes, Provence-Alpes-Côte d'Azur). Used as a CONSISTENCY
    # GUARD (candidate city's region must match the row's own already-derived region) as well as a
    # lookup -- a mismatch means the row's `city` text is a generic/mailing address, not the row's
    # true location, and the fix must abstain rather than assign a contradicting city.
    "Orsay": "Île-de-France",
    "Fontainebleau": "Île-de-France",
    "Villeneuve-d'Ascq": "Hauts-de-France",
    "Saint-Denis": "Île-de-France",
    "Sophia Antipolis": "Provence-Alpes-Côte d'Azur",
}

CITY_REGION_GAZETTEER: dict[str, str] = {_key(city): region for city, region in _CITY_REGION.items()}


def lookup_region_by_city(city: str | None) -> str | None:
    """Exact-match only: returns a region for a CLEAN commune name, None for anything else
    (full address, foreign city, unknown commune) -- never a substring/contains match."""
    if not city:
        return None
    return CITY_REGION_GAZETTEER.get(_key(city))
