"""Case 01: rule-heavy entity extraction. See spec.md (single source of truth)."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from harness import entities

CASE_ID = "01"
NAME = "Rule-heavy entity extraction"
SCHEMA_NAME = "companies"

LEGAL_SUFFIXES = ["AB", "GmbH", "AG", "Ltd", "PLC", "Inc.", "LLC", "Corp.", "AS", "ASA", "Oy", "Oyj", "A/S", "ApS",
                  "SA", "SAS", "B.V.", "N.V."]
NAME_WORDS = ["Group", "Systems", "Labs", "Partners", "Works", "Freight", "Energy", "Foods"]
PRODUCT_WORDS = {  # product word -> what the product is (for the generator)
    "Mail": "email service", "Pay": "payments app", "Cloud": "cloud storage service", "Drive": "fleet-tracking app",
    "Studio": "design software", "Connect": "messaging platform", "Hub": "smart-home controller",
    "Track": "parcel-tracking service", "Pulse": "fitness wearable", "Vault": "password manager",
    "Scan": "document-scanning app", "Flow": "workflow software", "Link": "router", "Sense": "air-quality sensor",
}
CITIES = {
    "en": ["London", "Manchester", "New York", "Chicago", "Austin", "Toronto", "Dublin", "Edinburgh",
           "Seattle", "Amsterdam", "Paris", "Stockholm", "Berlin", "Copenhagen", "Oslo", "Helsinki", "Zurich",
           "Rotterdam", "Lyon", "Leeds", "Denver"],
    "sv": ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Linköping", "Örebro", "Västerås", "Umeå", "Lund",
           "Luleå", "Jönköping", "Helsingborg", "Sundsvall", "Oslo", "Köpenhamn", "Helsingfors"],
    "de": ["Berlin", "München", "Hamburg", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig", "Dresden",
           "Hannover", "Nürnberg", "Bremen", "Wien", "Zürich", "Graz", "Basel"],
}
CATEGORIES = {
    "en": ["electric trucks", "payroll software", "heat pumps", "oat milk", "cargo bikes", "solar panels",
           "industrial robots", "cloud storage", "budget airlines", "smart meters", "wind turbines",
           "plant-based burgers", "e-scooters", "fintech apps", "security cameras", "battery packs",
           "meal kits", "drones", "workwear", "insurance policies"],
    "sv": ["elbilar", "värmepumpar", "havremjölk", "lastcyklar", "solpaneler", "industrirobotar", "molnlagring",
           "elsparkcyklar", "betalappar", "batterier", "vindkraftverk", "matkassar", "drönare", "arbetskläder",
           "smarta elmätare", "hemförsäkringar"],
    "de": ["Elektro-Lkw", "Wärmepumpen", "Hafermilch", "Lastenräder", "Solarmodule", "Industrieroboter",
           "Cloud-Speicher", "E-Scooter", "Bezahl-Apps", "Batteriespeicher", "Windräder", "Kochboxen", "Drohnen",
           "Arbeitskleidung", "Stromzähler", "Versicherungen"],
}
TITLES = {
    "en": ["chief executive", "chief financial officer", "founder", "analyst", "spokesperson", "head of sales",
           "union representative", "mayor", "economist", "chief technology officer", "customer"],
    "sv": ["vd", "finanschef", "grundare", "analytiker", "presstalesperson", "försäljningschef", "kommunalråd",
           "ekonom", "teknikchef", "kund"],
    "de": ["Vorstandschefin", "Finanzchef", "Gründer", "Analystin", "Sprecher", "Vertriebsleiterin",
           "Bürgermeister", "Ökonomin", "Technikchef", "Kundin"],
}
STYLES = ["a wire-service news brief", "a business-section feature", "a trade-magazine report",
          "a local newspaper item", "a market wrap", "a newsletter roundup", "a technology-desk news story",
          "a regional business column", "a news analysis piece", "a weekly industry digest entry"]
TOPICS = ["a new partnership", "a funding round", "quarterly results", "a product launch", "an expansion into a new market",
          "a supply-chain disruption", "a sustainability report", "a hiring drive", "a price war", "a trade fair",
          "a contract win", "a regulatory review", "a factory opening", "a cyber-security incident",
          "a customer survey", "a leadership change"]
OPENINGS = ["Open with a direct quote.", "Open with a number or statistic.", "Open with the place and date.",
            "Open with the main event.", "Open with a person.", "Open with background context.",
            "Open with a question a reader might have, then answer it.", "Open with a short scene."]
LANG_NAME = {"en": "English", "sv": "Swedish", "de": "German"}
TLDS = r"(?:se|de|com|co\.uk|no|fi|dk|fr|nl|ch|io|net|org|eu|at)"

SLICES = ["legal_suffix", "parent_present", "parent_absent", "sibling_products", "domain_forms", "diacritics",
          "distractors", "no_companies", "dense", "swedish", "german"]


# --------------------------------------------------------------------------- helpers

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def fold(s: str) -> str:
    return entities.ascii_fold(s).lower()


@lru_cache(maxsize=None)
def _all_companies() -> list[dict]:
    return entities.companies(pool=None)


@lru_cache(maxsize=None)
def _people_ok() -> list[dict]:
    names = {fold(w) for c in _all_companies() for w in c["name"].split()}
    return [p for p in entities.people() if fold(p["last"]) not in names]


def _one_word(c):
    return " " not in c["name"]


def _poss_ok(c):
    return _one_word(c) and not c["name"].endswith(("s", "x", "z"))


def _domain_only_ok(c):
    return _one_word(c) and not c["has_diacritics"]


# --------------------------------------------------------------------------- interface: slices and plan

def slices():
    return list(SLICES)


def slice_weights(variant):
    other = 70.0 / 9
    return {s: (20.0 if s == "swedish" else 10.0 if s == "german" else other) for s in SLICES}


def _mention(c, form, rng, lang, used_products):
    if form == "plain":
        return {"form": "plain", "text": c["name"]}
    if form == "legal":
        return {"form": "legal", "text": c["legal_name"]}
    if form == "possessive":
        return {"form": "possessive", "text": c["name"] + "'s"}
    if form == "product":
        word = rng.choice([w for w in PRODUCT_WORDS if w not in used_products])
        used_products.add(word)
        return {"form": "product", "text": f"{c['name']} {word}", "what": PRODUCT_WORDS[word]}
    if form == "domain":
        d = c["domain"]
        v = rng.choice(["bare", "bare", "www", "email"])
        if v == "www":
            d = "www." + d
        elif v == "email":
            d = rng.choice(["press", "info", "kontakt" if lang == "sv" else "contact", "ir"]) + "@" + d
        return {"form": "domain", "text": d}
    raise ValueError(form)


def _basic_form(c, rng, lang, allow_domain_only=False):
    """A random mention pattern for a company: list of forms."""
    opts = [("plain", 35), ("legal", 30)]
    if lang == "en" and _poss_ok(c):
        opts.append(("possessive", 15))
    if _one_word(c):
        opts.append(("product", 10))
    opts.append(("name+domain", 8))
    if allow_domain_only and _domain_only_ok(c):
        opts.append(("domain", 6))
    pick = rng.choices([o[0] for o in opts], weights=[o[1] for o in opts])[0]
    if pick == "name+domain":
        return [rng.choice(["plain", "legal"]), "domain"]
    if pick == "product" and rng.random() < 0.5:
        return [rng.choice(["plain", "legal"]), "product"]
    return [pick]


def plan(rng, slice, variant="main"):
    pool = entities.companies(pool="shift" if variant == "shift" else "main")
    lang = "sv" if slice == "swedish" else "de" if slice == "german" else "en"
    n = {"legal_suffix": (2, 5), "parent_present": (2, 5), "parent_absent": (1, 4), "sibling_products": (1, 4),
         "domain_forms": (2, 5), "diacritics": (2, 5), "distractors": (1, 4), "no_companies": (0, 0),
         "dense": (10, 12), "swedish": (2, 6), "german": (2, 6)}[slice]
    k = rng.randint(*n)
    chosen, firsts = [], set()

    def pick(pred):
        cands = [c for c in pool if pred(c) and fold(c["name"].split()[0]) not in firsts
                 and c["id"] not in {x["id"] for x in chosen}]
        c = rng.choice(cands)
        firsts.add(fold(c["name"].split()[0]))
        chosen.append(c)
        return c

    forms: dict[str, list[str]] = {}
    # the slice's defining companies first, then fill
    if slice == "legal_suffix":
        for _ in range(min(k, rng.randint(2, 3))):
            c = pick(lambda c: True)
            forms[c["id"]] = ["legal"] + (["plain"] if rng.random() < 0.4 else [])
    elif slice == "parent_present":
        c = pick(_one_word)
        forms[c["id"]] = [rng.choice(["plain", "legal"] + (["possessive"] if _poss_ok(c) else [])), "product"]
    elif slice == "parent_absent":
        c = pick(_one_word)
        forms[c["id"]] = ["product"]
    elif slice == "sibling_products":
        c = pick(_one_word)
        forms[c["id"]] = (["plain"] if rng.random() < 0.5 else []) + ["product", "product"]
    elif slice == "domain_forms":
        c = pick(_domain_only_ok)
        forms[c["id"]] = ["domain"]
        c = pick(lambda c: True)
        forms[c["id"]] = [rng.choice(["plain", "legal"]), "domain"]
    elif slice == "diacritics":
        for _ in range(rng.randint(1, 2)):
            c = pick(lambda c: c["has_diacritics"])
            forms[c["id"]] = rng.choice([["plain"], ["legal"], ["plain", "domain"], ["legal", "plain"]]
                                        + ([["possessive"]] if _poss_ok(c) else []))
    elif slice in ("swedish", "german"):
        home = "Sweden" if lang == "sv" else "Germany"
        for _ in range(min(k, 2)):
            c = pick(lambda c, h=home: c["country"] == h)
            forms[c["id"]] = _basic_form(c, rng, lang, allow_domain_only=True)
    while len(chosen) < k:
        if lang != "en" and rng.random() < 0.6:
            home = "Sweden" if lang == "sv" else "Germany"
            c = pick(lambda c, h=home: c["country"] == h)
        else:
            c = pick(lambda c: True)
        forms[c["id"]] = _basic_form(c, rng, lang, allow_domain_only=slice in ("dense", "swedish", "german"))
    rng.shuffle(chosen)
    comps = []
    for c in chosen:
        used: set = set()
        ms = [_mention(c, f, rng, lang, used) for f in forms[c["id"]]]
        comps.append({"id": c["id"], "name": c["name"], "sector": c["sector"], "country": c["country"],
                      "domain": c["domain"], "mentions": ms})
    # distractors
    n_people = rng.randint(3, 5) if slice in ("distractors", "no_companies") else rng.randint(0, 2)
    n_cities = rng.randint(2, 4) if slice in ("distractors", "no_companies") else rng.randint(0, 2)
    n_cats = rng.randint(2, 3) if slice in ("distractors", "no_companies") else rng.randint(0, 2)
    if variant == "shift":
        n_people, n_cities, n_cats = n_people + 1, n_cities + 1, n_cats + 1
    people = [{"name": p["name"], "title": rng.choice(TITLES[lang])} for p in rng.sample(_people_ok(), n_people)]
    cities = rng.sample(CITIES[lang], n_cities)
    cats = rng.sample(CATEGORIES[lang], n_cats)
    lo = rng.choice([120, 150, 180, 220]) if slice != "dense" else rng.choice([250, 280])
    hi = min(400, lo + rng.choice([100, 140, 180]))
    if variant == "shift":
        f = rng.choice([2.0, 2.5, 3.0])
        lo, hi = max(300, int(lo * f)), min(900, int(hi * f))
    return {"lang": lang, "companies": comps, "people": people, "cities": cities, "categories": cats,
            "words": [lo, hi], "style": rng.choice(STYLES), "topic": rng.choice(TOPICS),
            "opening": rng.choice(OPENINGS)}


# --------------------------------------------------------------------------- generation and verification

def _mention_instruction(c, m, only_this):
    t = m["text"]
    if m["form"] == "plain":
        return f'the name "{t}"'
    if m["form"] == "legal":
        return f'the full legal name "{t}"'
    if m["form"] == "possessive":
        return f'the possessive "{t}" (e.g. "{t} new office")'
    if m["form"] == "product":
        s = f'its product "{t}", a {m["what"]}, clearly presented as a product (e.g. "the {t} {m["what"].split()[-1]}")'
        return s
    if m["form"] == "domain":
        if "@" in t:
            return f'the email address "{t}"'
        return f'its website "{t}"'
    return t


def generator_prompt(plan):
    lang = LANG_NAME[plan["lang"]]
    lo, hi = plan["words"]
    lines = [f"Write {plan['style']} in {lang} about {plan['topic']}. Length: {lo}-{hi} words. "
             f"{plan['opening']}",
             "All company names below are fictional. Use them exactly as given (same spelling, capitalisation, "
             "diacritics and punctuation)."]
    if plan["companies"]:
        lines.append("\nCompanies (each must appear, each listed string must appear verbatim; mention the company only in the listed forms, as often as you like):")
        for c in plan["companies"]:
            ms = c["mentions"]
            forms = {m["form"] for m in ms}
            art = "An" if c["sector"][0] in "aeiou" else "A"
            desc = f'- {art} {c["sector"]} company from {c["country"]}. Mention it using ' + \
                "; and ".join(_mention_instruction(c, m, len(ms) == 1) for m in ms) + "."
            if forms <= {"product"}:
                desc += (f' Never write the company name "{c["name"]}" on its own; it appears only inside the '
                         "product name(s). Do not describe or refer to the maker separately (no \"a Finnish firm's "
                         "product\"); just mention the product itself.")
            if forms == {"domain"}:
                desc += (" Refer to this company only through that web address (e.g. \"the operator of "
                         f"{ms[0]['text']}\"); never write its name as a separate word.")
            if " " in c["name"]:
                desc += f' Always write the full name "{c["name"]}", never a shortened form.'
            lines.append(desc)
    else:
        lines.append("\nThe text must not name any company, brand or organisation at all; refer to businesses "
                     "only generically (e.g. \"a local bakery\", \"several manufacturers\").")
    if plan["people"]:
        lines.append("\nPeople to mention, each with their role worked naturally into the sentence (adapt the role "
                     "word to the grammar and the person; do not say which business employs them unless it is one of "
                     "the companies above): " + "; ".join(f'{p["name"]}, role: {p["title"]}' for p in plan["people"]))
    if plan["cities"]:
        lines.append("Places to mention: " + ", ".join(plan["cities"]) + ".")
    if plan["categories"]:
        lines.append("Product categories to mention generically: " + ", ".join(plan["categories"]) + ".")
    lines.append(
        "\nStrict rules:\n"
        "- Do not name any other company, brand, product, bank, stock exchange, news outlet, agency, university, "
        "government body or organisation, real or invented. Other businesses may only be described generically.\n"
        "- Do not add web addresses, email addresses or legal suffixes (AB, GmbH, Ltd, Inc. ...) other than the "
        "ones listed.\n"
        "- Do not write any company name in another spelling, without its diacritics, or in all capitals.\n"
        "- Output plain text only: no title, no headings, no bullet points, no Markdown, no notes.")
    return "\n".join(lines)


def make_input(plan, text):
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] == '"':
        t = t[1:-1].strip()
    return t


_DOMAIN_RE = re.compile(rf"(?<![\w.@-])(?:[a-z0-9-]+@)?((?:[a-z0-9-]+\.)+{TLDS})(?![\w-])", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"(?<![\w./])(AB|GmbH|AG|Ltd\.?|PLC|Inc\.?|LLC|Corp\.?|AS|ASA|Oy|Oyj|A/S|ApS|SA|SAS|"
                        r"B\.V\.|N\.V\.)(?![\w/])")


def _count(pattern: str, text: str, flags=0) -> int:
    """Word-bounded occurrences, excluding occurrences inside a domain or email address."""
    return len(re.findall(rf"(?<![\w@.]){pattern}(?![\w])(?!\.[a-z])", text, flags))


def verify(plan, text):
    words = len(text.split())
    lo, hi = plan["words"]
    if words < lo * 0.8 or words > hi * 1.2:
        return False, f"length {words} words outside {lo}-{hi}"
    for c in plan["companies"]:
        for m in c["mentions"]:
            t = m["text"]
            if t not in text and not (m["form"] == "possessive" and t.replace("'", "’") in text):
                return False, f"planned string missing: {t}"
    planned_names = [c["name"] for c in plan["companies"]]
    ftext = fold(text)
    # spelling variants (no diacritics, other case) and shortened two-word names
    for name in planned_names:
        exact = _count(re.escape(name), text)
        loose = _count(re.escape(fold(name)), ftext)
        if loose != exact:
            return False, f"variant spelling of {name}"
        if " " in name:
            first = fold(name.split()[0])
            if _count(re.escape(first), ftext) != exact:
                return False, f"shortened form of {name}"
    # unplanned companies from the entity lists
    tokens = set(re.findall(r"\w+", ftext))
    planned_tokens = {fold(w) for n in planned_names for w in n.split()}
    for c in _all_companies():
        if c["name"] in planned_names:
            continue
        ws = [fold(w) for w in c["name"].split()]
        if ws[0] in planned_tokens:
            continue
        if len(ws) == 1:
            hit = ws[0] in tokens
        else:
            hit = re.search(rf"\b{re.escape(' '.join(ws))}\b", ftext) is not None
        if hit or fold(c["domain"].split(".")[0]) in tokens:
            return False, f"unplanned company {c['name']}"
    # domains must be planned
    planned_domains = {c["domain"].lower() for c in plan["companies"]}
    for d in _DOMAIN_RE.findall(text):
        d = d.lower()
        if d.startswith("www."):
            d = d[4:]
        if d not in planned_domains:
            return False, f"unplanned domain {d}"
    # legal suffixes must follow a planned company name
    for m in _SUFFIX_RE.finditer(text):
        before = text[:m.start()].rstrip()
        if not any(before.endswith(n) for n in planned_names):
            return False, f"unplanned legal suffix {m.group(0)!r}"
    return True, ""


def verifier_brief(plan):
    exp = label(plan)
    if not exp:
        lines = ["The text must name NO company at all. The correct answer is an empty list."]
    else:
        lines = ["The task is to list every company named in the text. The correct answer is exactly these "
                 f"companies: {json.dumps(exp, ensure_ascii=False)}. They are mentioned through these forms:"]
        for c in plan["companies"]:
            lines.append(f'- {c["name"]}: ' + ", ".join(f'"{m["text"]}" ({m["form"]})' for m in c["mentions"]))
        lines.append("Product names like \"X Mail\" count as mentions of their parent company X; web and email "
                     "domains count as mentions of the company that owns them; legal suffixes (AB, GmbH, Ltd ...) "
                     "are part of the same company.")
    if plan["people"] or plan["cities"] or plan["categories"]:
        lines.append("People (" + ", ".join(p["name"] for p in plan["people"]) + "), places and generic product "
                     "categories are not companies and do not change the answer.")
    lines.append("The answer changes if the text names any other company, brand, bank, stock exchange, news "
                 "outlet, agency, university or other organisation (real or invented), if a planned product name "
                 "reads as an independent company rather than a product of its parent, or if a domain is not "
                 "clearly the planned company's website or email.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- label

def canonical(company: dict) -> str:
    """Rules 3-9 applied to one planned company."""
    forms = {m["form"] for m in company["mentions"]}
    if forms == {"domain"}:  # rule 8: named nowhere else
        d = company["mentions"][0]["text"].split("@")[-1]
        if d.startswith("www."):
            d = d[4:]
        lab = d.split(".")[0]
        return lab[:1].upper() + lab[1:]
    return company["name"]


def label(plan):
    out = []
    for c in plan["companies"]:
        n = canonical(c)
        if n not in out:
            out.append(n)
    return out


# --------------------------------------------------------------------------- request shape

def schema(settings):
    return {"type": "object", "properties": {"companies": {"type": "array", "items": {"type": "string"}}},
            "required": ["companies"], "additionalProperties": False}


# --------------------------------------------------------------------------- parse and score

_NONANSWER_RE = re.compile(r"\b(sorry|cannot|can't|unable|clarify|could you|please provide|which)\b", re.I)


def _salvage(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except Exception:
        return None
    return v if isinstance(v, list) and all(isinstance(x, str) for x in v) else None


def parse(output, settings, item):
    try:
        if isinstance(output, list):
            output = output[0] if output else {}
        output = output or {}
        text = output.get("text") or ""
        structured = bool((settings or {}).get("structured_outputs"))
        res = {"names": None, "kind": None, "salvaged": None, "nonanswer": False}
        if output.get("refusal"):
            res.update(kind="nonanswer", nonanswer=True)
            return res
        t = text.strip()
        if not t:
            res.update(kind="nonanswer", nonanswer=True)
            return res
        try:
            v = json.loads(t)
        except Exception:
            v = None
            sal = _salvage(t)
            res["salvaged"] = sal
            if t.startswith("```"):
                res["kind"] = "format_fence"
            elif sal is not None:
                res["kind"] = "prose_around"
            elif t.rstrip().endswith("?") or _NONANSWER_RE.search(t):
                res.update(kind="nonanswer", nonanswer=True)
            else:
                res["kind"] = "invalid_json"
            return res
        if structured and isinstance(v, dict) and set(v) == {"companies"}:
            v = v["companies"]
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            res.update(names=v, kind="ok")
        else:
            res["kind"] = "wrong_shape"
            if isinstance(v, dict) and isinstance(v.get("companies"), list):
                res["salvaged"] = [x for x in v["companies"] if isinstance(x, str)]
        return res
    except Exception:  # never raise
        return {"names": None, "kind": "invalid_json", "salvaged": None, "nonanswer": False}


def _classify_fp(fp: str, expected: list[str]) -> str:
    sufs = [s.rstrip(".") for s in LEGAL_SUFFIXES]
    if re.search(rf"\.{TLDS}$", fp, re.I) or "@" in fp:
        return "domain_not_mapped"
    for e in expected:
        if fp.startswith(e + " "):
            rest = fp[len(e) + 1:].strip().rstrip(".")
            if rest in sufs:
                return "legal_suffix_kept"
            if rest and rest.split()[0] in PRODUCT_WORDS:
                return "product_not_mapped"
        if fp in (e + "'s", e + "’s", e + "s"):
            return "possessive_kept"
        if fp != e and fold(fp) == fold(e):
            return "diacritics_lost" if fp.lower() != e.lower() else "case_changed"
    return "extra_company"


def score(expected, parsed):
    exp = [nfc(x) for x in expected]
    E = set(exp)
    p = parsed if isinstance(parsed, dict) else {"names": None, "kind": "invalid_json", "salvaged": None,
                                                  "nonanswer": False}
    names = p.get("names")
    valid = names is not None
    got = [nfc(x) for x in (names or [])]
    G = set(got)
    dup = len(got) - len(G)
    tp, fp, fn = len(E & G), len(G - E), len(E - G)
    passed = valid and dup == 0 and G == E
    cats: list[str] = []
    diag = got if valid else [nfc(x) for x in (p.get("salvaged") or [])]
    if not valid:
        cats.append(p.get("kind") or "invalid_json")
    if not passed:
        D = set(diag)
        explained = set()
        for x in sorted(D - E):
            c = _classify_fp(x, exp)
            cats.append(c)
            if c != "extra_company":
                explained |= {e for e in exp if fold(x).startswith(fold(e)) or fold(e) in fold(x)}
        if (E - D) - explained:
            cats.append("missing_company")
        if len(diag) != len(D):
            cats.append("duplicate")
    cats = list(dict.fromkeys(cats))
    diff = ""
    if not passed:
        if valid:
            diff = f"missing {sorted(E - G)}; extra {sorted(G - E)}" + (f"; {dup} duplicate(s)" if dup else "")
        else:
            diff = f"invalid ({p.get('kind')}); expected {exp}"
    return {"passed": passed, "valid": valid, "nonanswer": bool(p.get("nonanswer")),
            "secondary": {"tp": tp, "fp": fp, "fn": fn, "valid": int(valid), "duplicates": dup},
            "categories": cats, "diff": diff}


def aggregate(rows):
    tp = fp = fn = 0
    n = 0
    for r in rows:
        s = r.get("secondary") or {}
        if "tp" not in s:
            continue
        n += 1
        tp, fp, fn = tp + s["tp"], fp + s["fp"], fn + s["fn"]
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"micro_precision": prec, "micro_recall": rec, "micro_f1": f1,
            "format_validity": (sum(bool(r.get("valid")) for r in rows) / len(rows)) if rows else 0.0,
            "scored_items": n}


def failure_taxonomy():
    return ["format_fence", "prose_around", "invalid_json", "wrong_shape", "nonanswer", "missing_company",
            "extra_company", "legal_suffix_kept", "product_not_mapped", "domain_not_mapped", "possessive_kept",
            "diacritics_lost", "case_changed", "duplicate", "api_error", "other"]


def legacy_markers():
    return [r"\bNEVER\b", r"\bALWAYS\b", r"\bIMPORTANT\b", r"JSON array"]
