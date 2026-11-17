"""Invented entity lists, generated once from a fixed seed and stored in data/entities/.

2,000 companies (1,500 'main' + 500 'shift', the shift list is never used for train/dev/test),
500 people and 300 products. Names are built from syllables so they are fictional; real cities and
countries are used as-is.
"""
from __future__ import annotations

import json
import random
import unicodedata
from functools import lru_cache

from . import config

SEED = 20261117
ENT_DIR = config.DATA / "entities"

_ON = ["b", "br", "c", "d", "f", "g", "h", "j", "k", "kr", "l", "m", "n", "p", "r", "s", "st", "t", "tr", "v",
       "z", "sk", "gl", "pl", "dr", "fl"]
_NU = ["a", "e", "i", "o", "u", "a", "e", "o"]
_CO = ["", "", "", "", "n", "r", "l", "s", "m"]
_END = ["a", "ia", "ex", "on", "ora", "ix", "is", "ent", "ova", "um", "era", "yn", "ar", "eo", "ik", "ard"]
_DIAC = {"a": ["ä", "å", "á"], "o": ["ö", "ø", "ó"], "u": ["ü", "ú"], "e": ["é", "ë"]}

COUNTRIES = [  # (country, tld, legal suffixes, weight)
    ("Sweden", "se", ["AB"], 4), ("Germany", "de", ["GmbH", "AG"], 3), ("United Kingdom", "co.uk", ["Ltd", "PLC"], 3),
    ("United States", "com", ["Inc.", "LLC", "Corp."], 3), ("Norway", "no", ["AS", "ASA"], 1),
    ("Finland", "fi", ["Oy", "Oyj"], 1), ("Denmark", "dk", ["A/S", "ApS"], 1), ("France", "fr", ["SA", "SAS"], 1),
    ("Netherlands", "nl", ["B.V.", "N.V."], 1), ("Switzerland", "ch", ["AG", "SA"], 1),
]
SECTORS = ["logistics", "software", "payments", "retail", "energy", "biotech", "insurance", "media", "robotics",
           "foods", "telecom", "mining", "travel", "security", "analytics", "fashion", "construction", "gaming"]
FIRST = ["Anna", "Erik", "Lena", "Johan", "Maria", "Lars", "Sofia", "Karl", "Emma", "Nils", "Ida", "Oskar", "Clara",
         "Felix", "Hanna", "Jonas", "Lisa", "Paul", "Sara", "Tobias", "Julia", "David", "Elin", "Mats", "Greta",
         "Lukas", "Mia", "Henrik", "Alice", "Viktor", "Nora", "Simon", "Laura", "Anton", "Frida", "Max", "Ebba",
         "Leon", "Karin", "Hugo", "Amelia", "Omar", "Priya", "Chen", "Fatima", "Mateo", "Aisha", "Kenji", "Zara"]


def _syll(rng: random.Random) -> str:
    return rng.choice(_ON) + rng.choice(_NU) + rng.choice(_CO)


def _word(rng: random.Random, n: int) -> str:
    w = "".join(_syll(rng) for _ in range(n - 1)) + rng.choice(_ON) + rng.choice(_END)
    return w.capitalize()


def ascii_fold(s: str) -> str:
    s = s.replace("ß", "ss").replace("ø", "o").replace("Ø", "O").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _build() -> dict:
    rng = random.Random(SEED)
    names: set[str] = set()
    companies = []
    weights = [c[3] for c in COUNTRIES]
    while len(companies) < 2000:
        base = _word(rng, rng.choice([2, 2, 3]))
        if len(base) < 5 or len(base) > 12:
            continue
        diac = False
        if rng.random() < 0.12:
            idx = [i for i, ch in enumerate(base) if ch in _DIAC]
            if idx:
                i = rng.choice(idx)
                base = base[:i] + rng.choice(_DIAC[base[i]]) + base[i + 1:]
                diac = True
        name = base
        if rng.random() < 0.15:  # two-word names such as "Velmora Freight"
            name = f"{base} {rng.choice(['Group', 'Systems', 'Labs', 'Partners', 'Works', 'Freight', 'Energy', 'Foods'])}"
        key = ascii_fold(name).lower()
        if key in names:
            continue
        names.add(key)
        country, tld, suffixes, _ = rng.choices(COUNTRIES, weights=weights)[0]
        suffix = rng.choice(suffixes)
        companies.append({
            "id": f"C{len(companies):04d}", "name": name, "legal_suffix": suffix, "legal_name": f"{name} {suffix}",
            "country": country, "domain": ascii_fold(name).lower().replace(" ", "") + "." + tld,
            "sector": rng.choice(SECTORS), "has_diacritics": diac,
            "pool": "main" if len(companies) < 1500 else "shift",
        })
    people, pn = [], set()
    while len(people) < 500:
        first = rng.choice(FIRST)
        last = _word(rng, 2) + rng.choice(["", "", "son", "berg", "mann", "ström", "ton", "ez"])
        full = f"{first} {last}"
        if full in pn or len(last) > 14:
            continue
        pn.add(full)
        people.append({"id": f"P{len(people):03d}", "first": first, "last": last, "name": full})
    products, prn = [], set()
    while len(products) < 300:
        w = _word(rng, 2)
        if w.lower() in prn or w.lower() in names or len(w) > 10:
            continue
        prn.add(w.lower())
        products.append({"id": f"R{len(products):03d}", "name": w,
                         "category": rng.choice(["software", "device", "service", "chemical", "garment", "tool",
                                                 "beverage", "component"])})
    return {"companies": companies, "people": people, "products": products}


def build_and_save() -> None:
    ENT_DIR.mkdir(parents=True, exist_ok=True)
    d = _build()
    for k, v in d.items():
        (ENT_DIR / f"{k}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False), encoding="utf-8")


@lru_cache(maxsize=None)
def load(kind: str) -> list[dict]:
    p = ENT_DIR / f"{kind}.json"
    if not p.exists():
        build_and_save()
    return json.loads(p.read_text(encoding="utf-8"))


def companies(pool: str | None = "main") -> list[dict]:
    cs = load("companies")
    return [c for c in cs if pool is None or c["pool"] == pool]


def people() -> list[dict]:
    return load("people")


def products() -> list[dict]:
    return load("products")
