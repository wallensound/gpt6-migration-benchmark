"""Case 07: normalise one messy contact record into a fixed five-field JSON object under 18 rules.

Data are built entirely in code: a clean record is sampled (people and companies from harness.entities,
real countries), messy surface forms are applied, and the deterministic normaliser below (`normalise_record`)
turns the messy record into the expected output. The generator only writes natural notes around the record:
it places the line <<RECORD>> where the record goes and make_input substitutes the exact record lines, so the
record is always verbatim. verify() checks the record is present exactly once and the notes carry no values.
"""
from __future__ import annotations

import json
import re
import unicodedata

from harness import entities

CASE_ID = "07"
NAME = "contact normalisation under accumulated rules"
SCHEMA_NAME = "contact"
FIELDS = ["name", "phone", "email", "company", "country"]
PLACEHOLDER = "<<RECORD>>"

# --------------------------------------------------------------------------- countries
# iso2: (calling code, trunk prefix "0" used nationally, [(leading digits, NSN length, grouping)], tld,
#        English, Swedish, German, alpha-3, extra aliases)
COUNTRIES = {
    "SE": ("46", True, [("7", 9, [2, 3, 2, 2]), ("8", 9, [1, 3, 3, 2])], "se", "Sweden", "Sverige", "Schweden", "SWE", []),
    "DE": ("49", True, [("15", 11, [3, 4, 4]), ("17", 11, [3, 4, 4]), ("30", 10, [2, 4, 4])], "de", "Germany", "Tyskland",
           "Deutschland", "DEU", []),
    "GB": ("44", True, [("7", 10, [4, 6]), ("20", 10, [2, 4, 4])], "co.uk", "United Kingdom", "Storbritannien",
           "Vereinigtes Königreich", "GBR", ["UK", "Great Britain"]),
    "US": ("1", False, [("", 10, [3, 3, 4])], "com", "United States", "USA", "Vereinigte Staaten", "USA", ["U.S.A."]),
    "NO": ("47", False, [("4", 8, [3, 2, 3]), ("9", 8, [3, 2, 3])], "no", "Norway", "Norge", "Norwegen", "NOR", []),
    "FI": ("358", True, [("40", 9, [2, 3, 4]), ("50", 9, [2, 3, 4])], "fi", "Finland", "Finland", "Finnland", "FIN", []),
    "DK": ("45", False, [("2", 8, [2, 2, 2, 2]), ("4", 8, [2, 2, 2, 2])], "dk", "Denmark", "Danmark", "Dänemark", "DNK", []),
    "FR": ("33", True, [("6", 9, [1, 2, 2, 2, 2]), ("7", 9, [1, 2, 2, 2, 2])], "fr", "France", "Frankrike", "Frankreich",
           "FRA", []),
    "NL": ("31", True, [("6", 9, [1, 2, 3, 3])], "nl", "Netherlands", "Nederländerna", "Niederlande", "NLD", ["Holland"]),
    "CH": ("41", True, [("7", 9, [2, 3, 2, 2])], "ch", "Switzerland", "Schweiz", "Schweiz", "CHE", []),
    "ES": ("34", False, [("6", 9, [3, 3, 3])], "es", "Spain", "Spanien", "Spanien", "ESP", []),
    "IT": ("39", False, [("3", 10, [3, 3, 4])], "it", "Italy", "Italien", "Italien", "ITA", []),
    "PL": ("48", False, [("5", 9, [3, 3, 3]), ("6", 9, [3, 3, 3])], "pl", "Poland", "Polen", "Polen", "POL", []),
    "AT": ("43", True, [("664", 10, [3, 7]), ("676", 10, [3, 3, 4])], "at", "Austria", "Österrike", "Österreich", "AUT", []),
    "BE": ("32", True, [("47", 9, [3, 2, 2, 2]), ("49", 9, [3, 2, 2, 2])], "be", "Belgium", "Belgien", "Belgien", "BEL", []),
    "IE": ("353", True, [("8", 9, [2, 3, 4])], "ie", "Ireland", "Irland", "Irland", "IRL", []),
    # shift-only countries
    "JP": ("81", True, [("90", 10, [2, 4, 4]), ("80", 10, [2, 4, 4])], "co.jp", "Japan", "Japan", "Japan", "JPN", []),
    "BR": ("55", False, [("119", 11, [2, 5, 4]), ("219", 11, [2, 5, 4])], "com.br", "Brazil", "Brasilien", "Brasilien",
           "BRA", []),
    "MX": ("52", False, [("55", 10, [2, 4, 4]), ("33", 10, [2, 4, 4])], "com.mx", "Mexico", "Mexiko", "Mexiko", "MEX", []),
    "IN": ("91", True, [("9", 10, [5, 5]), ("8", 10, [5, 5])], "in", "India", "Indien", "Indien", "IND", []),
    "AU": ("61", True, [("4", 9, [3, 3, 3])], "com.au", "Australia", "Australien", "Australien", "AUS", []),
    "ZA": ("27", True, [("82", 9, [2, 3, 4]), ("83", 9, [2, 3, 4])], "co.za", "South Africa", "Sydafrika", "Südafrika",
           "ZAF", []),
    "GR": ("30", False, [("69", 10, [3, 3, 4])], "gr", "Greece", "Grekland", "Griechenland", "GRC", []),
    "TR": ("90", True, [("5", 10, [3, 3, 2, 2])], "com.tr", "Turkey", "Turkiet", "Türkei", "TUR", ["Türkiye"]),
    "NZ": ("64", True, [("21", 9, [2, 3, 4]), ("22", 9, [2, 3, 4])], "co.nz", "New Zealand", "Nya Zeeland", "Neuseeland",
           "NZL", []),
    "PT": ("351", False, [("91", 9, [3, 3, 3]), ("96", 9, [3, 3, 3])], "pt", "Portugal", "Portugal", "Portugal", "PRT", []),
    "CZ": ("420", False, [("60", 9, [3, 3, 3]), ("77", 9, [3, 3, 3])], "cz", "Czechia", "Tjeckien", "Tschechien", "CZE",
           ["Czech Republic"]),
    "KR": ("82", True, [("10", 10, [2, 4, 4])], "co.kr", "South Korea", "Sydkorea", "Südkorea", "KOR", []),
}
MAIN_COUNTRIES = ["SE", "DE", "GB", "US", "NO", "FI", "DK", "FR", "NL", "CH", "ES", "IT", "PL", "AT", "BE", "IE"]
MAIN_WEIGHTS = [4, 3, 3, 3, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1]
SHIFT_COUNTRIES = ["JP", "BR", "MX", "IN", "AU", "ZA", "GR", "TR", "NZ", "PT", "CZ", "KR"]
SHARED_CODES = {"1", "7"}  # calling codes shared by several countries: never used to infer a country

LEGAL_SUFFIXES = ["AB", "GmbH", "AG", "Ltd", "Ltd.", "PLC", "Inc", "Inc.", "LLC", "Corp", "Corp.", "AS", "ASA", "Oy",
                  "Oyj", "A/S", "ApS", "SA", "SAS", "B.V.", "N.V.", "S.p.A.", "Sp. z o.o.", "K.K.", "Pty Ltd", "Ltda."]
HONORIFICS = ["dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "prof", "prof.", "mx", "mx."]
PLACEHOLDERS = {"", "-", "--", "n/a", "na", "none", "unknown", "?", "null", "tbd"}

_ALIASES: dict[str, str] = {}
for _iso, _c in COUNTRIES.items():
    for _n in [_c[4], _c[5], _c[6], _c[7], _iso, *_c[8]]:
        _ALIASES[re.sub(r"[.\s]+", " ", _n.lower()).strip()] = _iso
_ALIASES["usa"] = "US"
_ALIASES["u s a"] = "US"


def _alias_key(s: str) -> str:
    return re.sub(r"[.\s]+", " ", s.lower()).strip()


# --------------------------------------------------------------------------- the normaliser (spec.md rules)

def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = re.sub(r"\s+", " ", unicodedata.normalize("NFC", v)).strip()
    return None if v.lower() in PLACEHOLDERS else v


_SUFFIX_RE = re.compile(r"(?:,\s*|\s+)(" + "|".join(re.escape(s) for s in sorted(LEGAL_SUFFIXES, key=len, reverse=True))
                        + r")$", re.IGNORECASE)
_EXT_RE = re.compile(r"\s*(?:ext\.?|extension|x|#)\s*\d{1,5}$", re.IGNORECASE)


def is_email(v: str) -> bool:
    return "@" in v


def _phone_core(v: str) -> str:
    v = re.sub(r"^tel:\s*", "", v.strip(), flags=re.IGNORECASE)
    return _EXT_RE.sub("", v).strip()


def is_phone(v: str) -> bool:
    core = _phone_core(v)
    return bool(re.fullmatch(r"[\d\s+\-().\/]+", core)) and len(re.sub(r"\D", "", core)) >= 7


def has_legal_suffix(v: str) -> bool:
    return bool(_SUFFIX_RE.search(v))


def norm_name(v: str | None) -> str | None:
    v = _clean(v)
    if not v:
        return None
    if "," in v:
        last, first = v.split(",", 1)
        v = f"{first.strip()} {last.strip()}".strip()
    parts = v.split(" ")
    while len(parts) > 1 and parts[0].lower() in HONORIFICS:
        parts = parts[1:]
    return " ".join("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")) for w in parts)


def norm_country(v: str | None) -> str | None:
    v = _clean(v)
    if not v:
        return None
    return _ALIASES.get(_alias_key(v))


def country_from_code(e164: str | None) -> str | None:
    if not e164:
        return None
    digits = e164[1:]
    for n in (3, 2, 1):
        code = digits[:n]
        if code in SHARED_CODES:
            return None
        hits = [iso for iso, c in COUNTRIES.items() if c[0] == code]
        if len(hits) == 1:
            return hits[0]
    return None


def is_international(v: str) -> bool:
    core = _phone_core(v).lstrip("( ")
    return core.startswith("+") or core.startswith("00")


def norm_phone(v: str | None, country: str | None) -> str | None:
    v = _clean(v)
    if not v:
        return None
    core = _phone_core(v)
    if is_international(core):
        core = core.replace("(0)", "")
        digits = re.sub(r"\D", "", core)
        if core.lstrip("( ").startswith("00"):
            digits = digits[2:]
        return "+" + digits
    if not country:
        return None
    digits = re.sub(r"\D", "", core)
    if digits.startswith("0"):
        digits = digits[1:]
    return "+" + COUNTRIES[country][0] + digits


def norm_email(v: str | None) -> str | None:
    v = _clean(v)
    if not v:
        return None
    v = re.sub(r"^mailto:\s*", "", v, flags=re.IGNORECASE).strip().strip("<>").strip()
    return v.lower()


def norm_company(v: str | None) -> str | None:
    v = _clean(v)
    if not v:
        return None
    v = _SUFFIX_RE.sub("", v).strip().rstrip(",").strip()
    return " ".join(w[:1].upper() + w[1:].lower() for w in v.split(" "))


def normalise_record(lines: list[list]) -> dict:
    """lines: [[field_label_kind, label_text, separator, raw_value], ...] in record order."""
    raw = {f: None for f in FIELDS}
    for kind, _lab, _sep, val in lines:
        raw[kind] = val
    vals = {f: _clean(raw[f]) for f in FIELDS}
    # rule 3: assign by content, not by label (phone/email swaps, name/company swaps)
    out_raw = {f: None for f in FIELDS}
    out_raw["country"] = vals["country"]
    pool = {f: vals[f] for f in ("name", "phone", "email", "company") if vals[f] is not None}
    rest = {}
    for f, v in pool.items():
        if is_email(v):
            out_raw["email"] = v
        elif is_phone(v):
            out_raw["phone"] = v
        else:
            rest[f] = v
    comp = [f for f, v in rest.items() if has_legal_suffix(v)]
    if "name" in comp and "company" in rest and "company" not in comp:  # name and company swapped
        out_raw["company"], out_raw["name"] = rest["name"], rest["company"]
    else:
        out_raw["name"], out_raw["company"] = rest.get("name"), rest.get("company")
    country = norm_country(out_raw["country"])
    phone = norm_phone(out_raw["phone"], country)
    if country is None and phone and out_raw["phone"] and is_international(out_raw["phone"]):
        country = country_from_code(phone)  # rule 16 (wins over rule 2 per the precedence note)
    return {"name": norm_name(out_raw["name"]), "phone": phone, "email": norm_email(out_raw["email"]),
            "company": norm_company(out_raw["company"]), "country": country}


# --------------------------------------------------------------------------- planning

UNICODE_FIRST = ["Åsa", "Björn", "Søren", "Zoë", "José", "Łukasz", "Øystein", "Jürgen", "Céline", "Inés", "Dagný",
                 "Göran", "Örjan", "Ágnes", "Mikaël", "Þóra", "Ævar", "Renée", "Žofie", "Ångel", "Íris", "Ömer"]
HYPHEN_FIRST = ["Anna-Lena", "Marie-Hélène", "Lise-Lotte", "Jean-Luc", "Eva-Marie", "Karl-Johan", "Ann-Sofie"]
_DIAC = {"a": ["ä", "å", "á"], "o": ["ö", "ø", "ó"], "u": ["ü", "ú"], "e": ["é", "ë"], "i": ["í"], "c": ["č"],
         "s": ["š"], "n": ["ñ"]}
FOLD = {"ł": "l", "Ł": "L", "þ": "th", "Þ": "Th", "ð": "d", "æ": "ae", "Æ": "Ae", "ø": "o", "Ø": "O", "ß": "ss"}
GENERIC_MAIL = ["gmail.com", "outlook.com", "proton.me", "hotmail.com", "icloud.com"]

LABELS = {
    "name": ["Name", "NAME", "Full name", "Contact", "Contact name", "name"],
    "phone": ["Phone", "Tel", "Mobile", "Phone no.", "PHONE", "Tel.", "Cell"],
    "email": ["Email", "E-mail", "Mail", "EMAIL", "e-mail", "Email address"],
    "company": ["Company", "Organisation", "Employer", "COMPANY", "Org", "Company name"],
    "country": ["Country", "COUNTRY", "Country/Region", "Land", "country"],
}
SEPS = [": ", ": ", ": ", ":  ", " : ", ":\t", " = "]


def fold(s: str) -> str:
    s = "".join(FOLD.get(ch, ch) for ch in s)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _digits(rng, n):
    return "".join(rng.choice("0123456789") for _ in range(n))


def make_nsn(rng, iso):
    lead, n, groups = rng.choice(COUNTRIES[iso][2])
    if iso == "US":
        lead = rng.choice("23456789") + _digits(rng, 2) + rng.choice("23456789")
    nsn = lead + _digits(rng, n - len(lead))
    if iso == "US":
        nsn = nsn[:6] + "01" + nsn[8:] if rng.random() < 0.5 else nsn
    return nsn, groups


def _group(s, groups):
    out, i = [], 0
    for g in groups:
        out.append(s[i:i + g])
        i += g
    if i < len(s):
        out[-1] += s[i:]
    return out


MAIN_INTL_FORMATS = ["plus_space", "plus_space", "plus_compact", "plus_dash", "zerozero_space"]
SLICE_INTL_FORMATS = ["zerozero_space", "zerozero_compact", "plus_trunk", "plus_ext", "plus_dash", "plus_dots_ext",
                      "zerozero_trunk"]
NAT_FORMATS = ["nat_space", "nat_dash", "nat_compact", "nat_paren"]
SHIFT_FORMATS = ["tel_uri", "paren_plus", "nat_slash", "zerozero_gap", "plus_dots", "plus_slash", "nat_dots",
                 "tel_uri_nat"]


def render_phone(rng, iso, nsn, groups, fmt):
    cc, trunk = COUNTRIES[iso][0], COUNTRIES[iso][1]
    g = _group(nsn, groups)
    nat = ("0" if trunk else "")
    if fmt == "plus_space":
        return f"+{cc} " + " ".join(g)
    if fmt == "plus_compact":
        return f"+{cc}{nsn}"
    if fmt == "plus_dash":
        return f"+{cc}-" + "-".join(g)
    if fmt == "zerozero_space":
        return f"00{cc} " + " ".join(g)
    if fmt == "zerozero_compact":
        return f"00{cc}{nsn}"
    if fmt == "plus_trunk":  # +44 (0)20 7946 0018; only meaningful with a trunk prefix
        return f"+{cc} (0)" + " ".join(g) if trunk else f"+{cc} " + " ".join(g)
    if fmt == "zerozero_trunk":
        return f"00{cc} (0)" + " ".join(g) if trunk else f"00{cc} " + " ".join(g)
    if fmt == "plus_ext":
        return f"+{cc} " + " ".join(g) + rng.choice([" ext. ", " ext ", " x", " #"]) + _digits(rng, rng.choice([2, 3, 4]))
    if fmt == "plus_dots_ext":
        return f"+{cc}." + ".".join(g) + rng.choice([" ext. ", " x"]) + _digits(rng, 3)
    if fmt == "nat_space":
        return nat + " ".join(g)
    if fmt == "nat_dash":
        return nat + g[0] + "-" + " ".join(g[1:])
    if fmt == "nat_compact":
        return nat + nsn
    if fmt == "nat_paren":
        return f"({nat}{g[0]}) " + " ".join(g[1:]) if len(g) > 2 else f"({nat}{g[0]}) {g[1]}"
    # shift-only formats
    if fmt == "tel_uri":
        return f"tel:+{cc}-" + "-".join(g)
    if fmt == "tel_uri_nat":
        return "tel:" + nat + "-".join(g)
    if fmt == "paren_plus":
        return f"(+{cc}) " + " ".join(g)
    if fmt == "nat_slash":
        return nat + g[0] + " / " + "".join(g[1:])
    if fmt == "zerozero_gap":
        return f"00 {cc} " + " ".join(g)
    if fmt == "plus_dots":
        return f"+{cc}." + ".".join(g)
    if fmt == "plus_slash":
        return f"+{cc}/" + "".join(g)
    if fmt == "nat_dots":
        return nat + ".".join(g)
    raise ValueError(fmt)


def _casing(rng, s, p_upper=0.2, p_lower=0.25):
    r = rng.random()
    if r < p_upper:
        return s.upper()
    if r < p_upper + p_lower:
        return s.lower()
    return s


def _ws(rng, s, p=0.3):
    if rng.random() < p and " " in s:
        s = s.replace(" ", rng.choice(["  ", "   "]), 1)
    if rng.random() < p * 0.7:
        s = rng.choice([" ", "  "]) + s
    if rng.random() < p * 0.5:
        s = s + rng.choice([" ", "  "])
    return s


def slices():
    return ["plain", "precedence_conflict", "international_phone", "missing_fields", "unicode_names", "swapped_fields"]


def _country_form(rng, iso, variant):
    c = COUNTRIES[iso]
    r = rng.random()
    if r < 0.3:
        s = c[4]
    elif r < 0.6:
        s = c[5]
    elif r < 0.88:
        s = c[6]
    elif r < 0.94:
        s = c[7]
    else:
        s = iso
    if c[8] and rng.random() < 0.25:
        s = rng.choice(c[8])
    return _ws(rng, _casing(rng, s, 0.15, 0.15), 0.2)


def plan(rng, slice, variant="main"):
    shift = variant == "shift"
    people = entities.people()
    comps = entities.companies("shift" if shift else "main")
    person = rng.choice(people)
    company = rng.choice(comps)
    iso = rng.choice(SHIFT_COUNTRIES) if shift else rng.choices(MAIN_COUNTRIES, weights=MAIN_WEIGHTS)[0]
    if slice == "precedence_conflict" and iso == "US":
        iso = "GB"
    first, last = person["first"], person["last"]
    if slice == "unicode_names":
        r = rng.random()
        if r < 0.45:
            first = rng.choice(UNICODE_FIRST)
        elif r < 0.65:
            first = rng.choice(HYPHEN_FIRST)
        if r >= 0.45 or rng.random() < 0.6:
            idx = [i for i, ch in enumerate(last) if ch in _DIAC and i > 0]
            if idx:
                i = rng.choice(idx)
                last = last[:i] + rng.choice(_DIAC[last[i]]) + last[i + 1:]
        if all(ch.isascii() for ch in first + last):
            first = rng.choice(UNICODE_FIRST)
    clean_name = f"{first} {last}"
    nsn, groups = make_nsn(rng, iso)
    phone_iso = iso
    if slice == "international_phone" and rng.random() < 0.3:  # rule 18: phone from another country
        pool = SHIFT_COUNTRIES if shift else MAIN_COUNTRIES
        phone_iso = rng.choice([c for c in pool if c != iso])
        nsn, groups = make_nsn(rng, phone_iso)
    # ---- surface forms
    # name
    nm = clean_name
    nm_form = "first_last"
    if rng.random() < (0.45 if slice == "unicode_names" else 0.3):
        nm = f"{last}, {first}"
        nm_form = "last_comma_first"
    elif rng.random() < 0.15:
        nm = rng.choice(["Dr.", "Dr", "Mr", "Ms.", "Mrs", "Prof.", "Ms"]) + " " + nm
        nm_form = "honorific"
    nm = _ws(rng, _casing(rng, nm, 0.3 if slice == "unicode_names" else 0.2,
                          0.35 if slice == "unicode_names" else 0.25))
    # phone
    if shift and rng.random() < 0.6:
        fmt = rng.choice(SHIFT_FORMATS)
    elif slice == "international_phone":
        fmt = rng.choice(SLICE_INTL_FORMATS)
    elif slice == "precedence_conflict":
        fmt = rng.choice(MAIN_INTL_FORMATS + ["zerozero_compact", "plus_trunk"])
    else:
        fmt = rng.choice(MAIN_INTL_FORMATS + NAT_FORMATS + NAT_FORMATS)
    if phone_iso != iso or slice == "precedence_conflict":  # these must be international
        if fmt in NAT_FORMATS or fmt in ("nat_slash", "nat_dots", "tel_uri_nat"):
            fmt = rng.choice(["plus_space", "zerozero_space", "tel_uri" if shift else "plus_dash"])
    ph = render_phone(rng, phone_iso, nsn, groups, fmt)
    ph = _ws(rng, ph, 0.15)
    # email
    base = company["name"]
    tld = COUNTRIES[iso][3]
    dom = (fold(base).lower().replace(" ", "") + "." + tld) if rng.random() < 0.8 else rng.choice(GENERIC_MAIL)
    f_, l_ = fold(first).lower(), fold(last).lower()
    local = rng.choice([f"{f_}.{l_}", f"{f_[0]}.{l_}", f"{f_}{l_[0]}", f"{f_}_{l_}", f"{f_}"])
    clean_email = f"{local}@{dom}"
    em = clean_email
    r = rng.random()
    if r < 0.2:
        em = em.upper()
    elif r < 0.45:
        lp, d = em.split("@")
        em = ".".join(p.capitalize() for p in lp.split(".")) + "@" + d.capitalize()
    r = rng.random()
    if r < 0.1:
        em = "mailto:" + em
    elif r < 0.2:
        em = f"<{em}>"
    em = _ws(rng, em, 0.2)
    # company
    suffix = company["legal_suffix"] if not shift else rng.choice(LEGAL_SUFFIXES)
    with_suffix = rng.random() < 0.6
    if slice == "swapped_fields":
        with_suffix = True
    co = base
    if with_suffix:
        co = base + rng.choice([" ", " ", ", "]) + suffix
    co = _ws(rng, _casing(rng, co, 0.2, 0.2), 0.25)
    # country
    ct = _country_form(rng, iso, variant)
    values = {"name": nm, "phone": ph, "email": em, "company": co, "country": ct}
    # ---- slice specifics
    missing = []
    swap = None
    if slice == "precedence_conflict":
        missing = ["country"]
    elif slice == "missing_fields":
        k = 1 if rng.random() < 0.6 else 2
        missing = rng.sample(["phone", "email", "company", "country"], k)
        if "country" in missing and "phone" not in missing:
            missing.append("phone")
    elif slice == "swapped_fields":
        r = rng.random()
        swap = "phone_email" if r < 0.45 else ("name_company" if r < 0.85 else "both")
    if slice in ("plain", "international_phone", "unicode_names") and rng.random() < 0.08:
        missing = [rng.choice(["email", "company"])]
    label_kind = {f: f for f in FIELDS}  # which field's value sits under which label
    if swap in ("phone_email", "both"):
        label_kind["phone"], label_kind["email"] = "email", "phone"
    if swap in ("name_company", "both"):
        label_kind["name"], label_kind["company"] = "company", "name"
    lines = []
    order = list(FIELDS)
    if rng.random() < 0.3:
        rng.shuffle(order)
    for lab_f in order:
        val_f = label_kind[lab_f]
        if val_f in missing:
            if rng.random() < 0.5:
                continue
            val = rng.choice(["", "-", "n/a", "N/A", "unknown", "none", "?", "TBD"])
        else:
            val = values[val_f]
        # the line belongs to the label; normaliser input uses the label's field
        lines.append([lab_f, rng.choice(LABELS[lab_f]), rng.choice(SEPS), val])
    clean = {"name": clean_name,
             "phone": None if "phone" in missing else "+" + COUNTRIES[phone_iso][0] + nsn,
             "email": None if "email" in missing else clean_email,
             "company": None if "company" in missing else " ".join(w[:1].upper() + w[1:] for w in base.split(" ")),
             "country": None if ("country" in missing and "phone" in missing) else iso}
    return {
        "record_lines": lines, "clean": clean, "first_name": first, "last_name": last, "company_base": base,
        "sector": company["sector"], "country_iso": iso, "phone_iso": phone_iso, "phone_format": fmt,
        "name_form": nm_form, "missing": missing, "swap": swap,
        "style": _style(rng), "mention_first": rng.random() < 0.5,
    }


SCENARIOS = [
    "a contact captured from a badge scan at a trade fair, forwarded for CRM import",
    "an inbound demo request copied out of a web form, sent to sales ops",
    "a row pasted from an old spreadsheet export during a CRM clean-up",
    "a business card a colleague photographed and typed up after a meeting",
    "a lead handed over from a partner, pasted into a support ticket",
    "a duplicate-merge request from the data quality queue",
    "a webinar registration that needs to go into the mailing system",
    "a contact a salesperson added in a hurry from their phone",
    "a supplier contact that procurement wants added to the vendor list",
    "a contact from a customer-success handover note",
    "a referral passed on in a chat message",
    "an onboarding checklist item asking for the contact to be entered",
]
STYLES = [
    "a terse internal ticket", "a chatty internal email", "a short chat message", "a short note with a few bullet points",
    "a forwarded email with a one-line intro", "a CRM activity note", "a polite request from a junior colleague",
    "a slightly impatient message from a manager",
]
PLACEMENTS = ["near the start, after one short intro sentence", "in the middle, between two short paragraphs",
              "at the end, after the notes", "after a greeting and one sentence of context"]


def _style(rng):
    return {"scenario": rng.choice(SCENARIOS), "style": rng.choice(STYLES), "placement": rng.choice(PLACEMENTS),
            "words": rng.choice([30, 45, 60, 80, 100])}


def record_text(plan) -> str:
    return "\n".join(f"{lab}{sep}{val}" for _k, lab, sep, val in plan["record_lines"])


def generator_prompt(plan) -> str:
    st = plan["style"]
    who = (f"You may refer to the contact by the first name \"{plan['first_name']}\" (exactly that spelling) or as "
           "\"they\" / \"this contact\"." if plan["mention_first"] else
           "Refer to the contact only as \"they\", \"this person\" or \"this contact\"; do not use any name.")
    return f"""Write the text of {st['style']} about {st['scenario']}. The contact works in {plan['sector']}.

A contact record will be inserted into your text by a program. Put the exact line {PLACEHOLDER} on its own line, \
{st['placement']}. Write {PLACEHOLDER} exactly once and do not write any of the record's contents yourself.

{who}

Strict rules for your text (outside the {PLACEHOLDER} line):
- No phone numbers, no email addresses, no web addresses, and no numbers longer than four digits.
- No company or organisation names, no other people's names (sign off with a role such as "Sales ops" if needed), \
no surnames.
- No countries, cities, regions, nationalities, languages or time zones.
- Do not state, correct or hint at any value of the contact (name, phone, email, company, country), and do not say \
which details are missing, wrong or in the wrong place. A general remark such as "the export is a bit messy" is fine.
- Do not tell the reader how to format anything.
- About {st['words']} words. Plain text only: no Markdown, no code blocks, no headings, no quotation marks around \
the {PLACEHOLDER} line.

Output only the text."""


def make_input(plan, text) -> str:
    text = text.strip()
    if text.count(PLACEHOLDER) != 1:
        return text  # verify() rejects it
    lines = text.split("\n")
    out = []
    for ln in lines:
        if PLACEHOLDER in ln:
            if ln.strip() != PLACEHOLDER:
                return text
            out.append(record_text(plan))
        else:
            out.append(ln)
    return "\n".join(out)


_COUNTRY_WORDS = sorted({w for c in COUNTRIES.values() for w in [c[4], c[5], c[6], *c[8]] if len(w) >= 4}
                        | {c[7] for c in COUNTRIES.values()})


def verify(plan, text):
    rec = record_text(plan)
    if PLACEHOLDER in text:
        return False, "placeholder not substituted (missing on its own line or repeated)"
    if text.count(rec) != 1:
        return False, "record block not present exactly once"
    notes = text.replace(rec, "\n")
    if not notes.strip():
        return False, "no notes around the record"
    if "@" in notes:
        return False, "email-like text outside the record"
    if re.search(r"https?://|www\.", notes):
        return False, "web address in notes"
    for m in re.finditer(r"[+\d][\d\s\-().\/]*\d", notes):
        if len(re.sub(r"\D", "", m.group())) >= 5:
            return False, f"number in notes: {m.group()!r}"
    low = notes.lower()
    for w in _COUNTRY_WORDS:
        flags = 0 if w.isupper() else re.IGNORECASE
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", notes, flags):
            return False, f"country word in notes: {w}"
    for w in [plan["last_name"], plan["company_base"].split(" ")[0]]:
        if re.search(rf"(?<!\w){re.escape(fold(w).lower())}(?!\w)", fold(low)):
            return False, f"record value in notes: {w}"
    if not plan["mention_first"] and re.search(rf"(?<!\w){re.escape(plan['first_name'].lower())}(?!\w)", low):
        return False, "first name in notes"
    if "```" in text or re.search(r"^#+\s", notes, re.MULTILINE):
        return False, "markdown in notes"
    return True, ""


def verifier_brief(plan) -> str:
    exp = label(plan)
    notes = [
        "The TEXT contains notes written around a contact record (the 'Label: value' lines). The record is "
        "deliberately messy (casing, spacing, phone formats, country names in English, Swedish or German, legal "
        "suffixes); that is intended and is NOT a problem. The answer is derived from the record lines only.",
        f"Correct normalised output: {json.dumps(exp, ensure_ascii=False)}",
    ]
    if plan["swap"]:
        notes.append("Some values sit under the wrong label on purpose (e.g. the email under the phone label, or the "
                     "company under the name label); values are assigned by their content. That is intended.")
    if plan["missing"]:
        notes.append(f"These fields are deliberately absent or placeholders: {', '.join(plan['missing'])}.")
    if plan["slice"] == "precedence_conflict":
        notes.append("The country field is empty on purpose; by rule the country is taken from the phone's "
                     "international calling code. Nothing in the notes may name or hint at a country or place.")
    if plan["phone_iso"] != plan["country_iso"]:
        notes.append("The phone's calling code belongs to a different country than the country field; by rule the "
                     "country field wins and the phone keeps its own code. That is intended.")
    notes.append("Flag the item only if the NOTES (outside the record lines) add a competing or extra value: another "
                 "person, company, phone, email, country, city or nationality; a correction of a record value; or "
                 "anything that hints at a value for a field that is absent. A first name matching the record is fine.")
    return "\n".join(notes)


def label(plan) -> dict:
    return normalise_record(plan["record_lines"])


# --------------------------------------------------------------------------- scoring

def schema(settings):
    return {"type": "object",
            "properties": {f: {"type": ["string", "null"]} for f in FIELDS},
            "required": list(FIELDS), "additionalProperties": False}


FORMAT_RE = {
    "name": re.compile(r"^\S(.*\S)?$"),
    "phone": re.compile(r"^\+[1-9]\d{6,14}$"),
    "email": re.compile(r"^[^\sA-Z@]+@[^\sA-Z@]+\.[^\sA-Z@]+$"),
    "company": re.compile(r"^\S(.*\S)?$"),
    "country": re.compile(r"^[A-Z]{2}$"),
}


def _salvage(text: str):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def parse(output, settings, item):
    if isinstance(output, list):
        output = output[0] if output else {}
    text = (output.get("text") or "") if isinstance(output, dict) else ""
    refusal = output.get("refusal") if isinstance(output, dict) else None
    t = text.strip()
    obj, strict = None, False
    try:
        o = json.loads(t)
        if isinstance(o, dict):
            obj, strict = o, True
    except Exception:
        obj = _salvage(t)
    return {"obj": obj, "strict_json": strict, "fenced": t.startswith("```"), "text": text[:2000],
            "refusal": refusal}


def _nfc(v):
    return unicodedata.normalize("NFC", v) if isinstance(v, str) else v


def score(expected, parsed) -> dict:
    parsed = parsed or {}
    obj = parsed.get("obj")
    text = (parsed.get("text") or "").strip()
    nonanswer = bool(parsed.get("refusal")) or not text or (obj is None and text.endswith("?"))
    keys_ok = isinstance(obj, dict) and set(obj) == set(FIELDS) and all(v is None or isinstance(v, str)
                                                                         for v in obj.values())
    valid = bool(parsed.get("strict_json")) and keys_ok
    got = obj if isinstance(obj, dict) else {}
    correct, fmt_ok, cats, diffs = {}, {}, [], []
    for f in FIELDS:
        e, g = _nfc(expected.get(f)), _nfc(got.get(f))
        correct[f] = (e == g) and (f in got)
        fmt_ok[f] = g is None or (isinstance(g, str) and bool(FORMAT_RE[f].match(g)))
        if not correct[f] and obj is not None:
            diffs.append(f"{f}: expected {e!r}, got {g!r}")
            if e is None:
                cats.append("invented_value")
            elif g is None:
                cats.append("dropped_value")
            else:
                cats.append(f"{f}_wrong")
    passed = valid and all(correct.values())
    if nonanswer:
        cats = ["nonanswer"]
    elif not valid:
        cats = ["format"] + cats
    diff = "; ".join(diffs)
    if not valid and not nonanswer:
        diff = ("not a bare JSON object with exactly the five keys" + ("; fenced" if parsed.get("fenced") else "")
                + ("; " + diff if diff else ""))
    if nonanswer:
        diff = f"nonanswer: {text[:120]!r}"
    n_ok = sum(correct.values()) if obj is not None else 0
    return {"passed": passed, "valid": valid, "nonanswer": nonanswer,
            "secondary": {"fields_correct": n_ok, "fields_total": len(FIELDS),
                          "field_accuracy": n_ok / len(FIELDS),
                          "format_valid_fields": sum(fmt_ok.values()) if obj is not None else 0,
                          **{f"{f}_correct": int(correct[f]) if obj is not None else 0 for f in FIELDS}},
            "categories": sorted(set(cats)), "diff": diff}


def aggregate(rows) -> dict:
    n = len(rows)
    if not n:
        return {}
    tot = len(FIELDS) * n
    ok = sum((r.get("secondary") or {}).get("fields_correct", 0) for r in rows)
    fv = sum((r.get("secondary") or {}).get("format_valid_fields", 0) for r in rows)
    out = {"field_accuracy": ok / tot, "format_validity": fv / tot,
           "json_validity": sum(bool(r.get("valid")) for r in rows) / n}
    for f in FIELDS:
        out[f"{f}_accuracy"] = sum((r.get("secondary") or {}).get(f"{f}_correct", 0) for r in rows) / n
    return out


def failure_taxonomy():
    return ["format", "nonanswer", "name_wrong", "phone_wrong", "email_wrong", "company_wrong", "country_wrong",
            "invented_value", "dropped_value", "other"]


def legacy_markers():
    return [
        r"^IMPORTANT",                               # the IMPORTANT block
        r"PRECEDENCE",                               # precedence note settling the conflicting rules
        r"NEVER guess or infer",                     # rule A of the conflicting pair
        r"(?s)NEVER guess or infer.*NEVER guess or infer",  # ... stated twice (duplicate)
        r"(?s)E\.164.*E\.164.*E\.164",              # phone rule duplicated across sections
        r"(?s)(lowercase|lower-case).*(lowercase|lower-case)",  # email rule duplicated
        r"ALWAYS",
        r"(?i)be concise",
    ]
