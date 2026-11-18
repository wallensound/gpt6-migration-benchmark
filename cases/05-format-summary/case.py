"""Case 05: format-constrained summary.

Summarise a news article into exactly three plain-text bullets ("- ", <= 20 words each) that cover three
planted key facts: a number, a named entity and a date. See spec.md (single source of truth).
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

from harness import entities

CASE_ID = "05"
NAME = "Format-constrained summary"

# ----------------------------------------------------------------------------------------------- constants

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
             "november", "december"]
_MONTH_KEYS = {}
for _i, (_en, _sv) in enumerate(zip(MONTHS_EN, MONTHS_SV), start=1):
    _MONTH_KEYS[_en.lower()] = _i
    _MONTH_KEYS[_sv] = _i
    _MONTH_KEYS[_en[:3].lower()] = _i
_MONTH_KEYS["sept"] = 9
_MONTH_RE = "|".join(sorted(_MONTH_KEYS, key=len, reverse=True))

SWEDISH_STOPWORDS = {"och", "att", "är", "som", "för", "med", "på", "av", "det", "har", "kommer", "inte", "ett",
                     "vid", "hos", "enligt", "också", "från", "efter", "eller", "detta", "även"}

CITIES = {
    "Sweden": ["Gothenburg", "Malmö", "Uppsala", "Västerås", "Örebro", "Linköping", "Umeå", "Luleå", "Gävle",
               "Jönköping", "Sundsvall", "Karlstad"],
    "Germany": ["Leipzig", "Hamburg", "Dresden", "Hanover", "Bremen", "Nuremberg"],
    "United Kingdom": ["Leeds", "Bristol", "Manchester", "Glasgow", "Cardiff", "Sheffield"],
    "United States": ["Columbus", "Denver", "Pittsburgh", "Raleigh", "Austin", "Milwaukee"],
    "Norway": ["Bergen", "Trondheim", "Stavanger"], "Finland": ["Tampere", "Oulu", "Turku"],
    "Denmark": ["Aarhus", "Odense", "Aalborg"], "France": ["Lyon", "Lille", "Nantes"],
    "Netherlands": ["Eindhoven", "Utrecht", "Groningen"], "Switzerland": ["Basel", "Winterthur", "Lausanne"],
}
SWEDISH_CITIES = CITIES["Sweden"]
FACILITIES = ["factory", "logistics centre", "data centre", "battery plant", "warehouse", "research centre"]

# Each story: what the article is about and the three key facts.
# num = (what the figure is, unit_en, unit_sv, lo, hi); ent = (kind, role); date = event
STORIES = {
    "plant": {"about": "{S}, a {sector} company, will build a new {facility} in {city}",
              "num": ("the number of new jobs the {facility} will create", "new jobs", "nya jobb", 150, 4800),
              "ent": ("company", "the partner company that will build and co-run the {facility} with {S}"),
              "date": "the day production at the {facility} starts"},
    "acquisition": {"about": "{S}, a {sector} company, has agreed to buy another company",
                    "num": ("the purchase price", "million euros", "miljoner euro", 120, 980),
                    "ent": ("company", "the company being acquired by {S}"),
                    "date": "the day the deal is expected to close"},
    "ceo": {"about": "{S}, a {sector} company, has named a new chief executive",
            "num": ("the size of the cost-savings programme the new chief executive must deliver", "million kronor",
                    "miljoner kronor", 60, 950),
            "ent": ("person", "the new chief executive of {S}"),
            "date": "the day the new chief executive takes over"},
    "launch": {"about": "{S}, a {sector} company, is launching a new product",
               "num": ("the launch price of the product", "euros", "euro", 49, 2400),
               "ent": ("product", "the name of the new product made by {S}"),
               "date": "the day the product goes on sale"},
    "trial": {"about": "{S}, a biotech company, reports results from a large clinical trial",
              "num": ("the number of patients in the trial", "patients", "patienter", 120, 6500),
              "ent": ("person", "the trial's lead investigator"),
              "date": "the day {S} will submit the results to regulators"},
    "contract": {"about": "{S}, a {sector} company, has won the largest contract in its history",
                 "num": ("the value of the contract", "million euros", "miljoner euro", 45, 900),
                 "ent": ("company", "the customer that awarded the contract to {S}"),
                 "date": "the day deliveries under the contract begin"},
    "cuts": {"about": "{S}, a {sector} company, will cut jobs in a restructuring",
             "num": ("the number of jobs being cut", "jobs", "tjänster", 60, 3900),
             "ent": ("person", "the newly appointed head of operations who will lead the restructuring at {S}"),
             "date": "the day the job cuts take effect"},
    "funding": {"about": "{S}, a young {sector} company, has raised a large funding round",
                "num": ("the size of the funding round", "million euros", "miljoner euro", 40, 480),
                "ent": ("company", "the investment firm leading the funding round"),
                "date": "the day {S} opens its first office abroad with the money"},
    "recall": {"about": "{S}, a {sector} company, is recalling one of its products",
               "num": ("the number of units being recalled", "units", "enheter", 1200, 85000),
               "ent": ("product", "the name of the recalled product made by {S}"),
               "date": "the last day customers can return the product for a full refund"},
    "fleet": {"about": "{S}, a regional public transport operator, is buying electric buses",
              "num": ("the number of electric buses ordered", "electric buses", "elbussar", 40, 650),
              "ent": ("company", "the bus manufacturer supplying the buses"),
              "date": "the day the first new buses enter service"},
    "stores": {"about": "{S}, a {sector} retail company, will open new shops",
               "num": ("the number of new shops", "new stores", "nya butiker", 40, 320),
               "ent": ("company", "the franchise partner that will run the new shops for {S}"),
               "date": "the day the first new shop opens"},
}

DISTRACTOR_ROLES = [
    ("a press officer at {S}", "makes a brief, general remark about the company's values"),
    ("a local councillor", "welcomes the news in general terms"),
    ("an industry analyst", "notes in passing that the sector has had a busy year"),
    ("the chair of the staff sports club at {S}", "mentions the club's football team"),
    ("a long-time customer", "says in passing that the company's service has always been friendly"),
    ("a retired former employee of {S}", "shares a short memory of the old headquarters"),
]
DISTRACTOR_NUMBERS = [  # (unit_en, unit_sv, lo, hi, context)
    ("parking spaces", "parkeringsplatser", 40, 900, "the visitor car park at the headquarters"),
    ("square metres", "kvadratmeter", 1200, 9000, "the floor area of the head office building"),
    ("visitors", "besökare", 120, 4000, "attendance at last year's open day"),
    ("trees", "träd", 50, 2500, "trees planted around the headquarters in a greening project"),
    ("kilometres", "kilometer", 8, 95, "the distance from the headquarters to the nearest airport"),
    ("cups of coffee", "koppar kaffe", 200, 3000, "served daily in the staff café"),
    ("years", "år", 12, 140, "the age of the company's oldest building"),
    ("percent", "procent", 5, 35, "the share of staff who cycle to work"),
    ("bicycles", "cyklar", 30, 400, "the number of bicycle stands outside the office"),
    ("books", "böcker", 300, 6000, "the size of the staff library"),
]
DISTRACTOR_DATES = [  # (event, tense)
    ("an open house the company held for neighbours", "past"),
    ("the publication of the company's previous quarterly report", "past"),
    ("a trade fair the company attended", "past"),
    ("the company's annual staff summer party", "past"),
    ("a planned charity run organised by staff", "future"),
    ("a planned visit by a group of school pupils", "future"),
]

OUTLETS = ["a regional daily newspaper", "a trade magazine for the {sector} industry", "a business news wire",
           "a local news website", "a weekly business magazine", "the business section of a national newspaper"]
TONES = ["neutral and factual", "lively, feature-style", "dry and formal", "slightly sceptical and analytical",
         "warm and community-focused"]
OPENINGS = ["open with the news itself", "open with a short scene at the company", "open with context about the market",
            "open with a question a reader might have"]
QUOTES = ["include one short quote", "include two short quotes", "use no direct quotes"]

WORD_BANDS = {  # slice/variant -> (target_lo, target_hi, accept_lo, accept_hi)
    "main": (480, 650, 400, 900),
    "long": (780, 860, 700, 900),
    "shift": (1700, 1900, 1500, 2000),
}

# ----------------------------------------------------------------------------------------------- slices


def slices():
    return ["plain", "facts_near_end", "numbers_heavy", "long_articles", "swedish_source"]


def shift_slices():
    return ["plain", "facts_near_end", "numbers_heavy", "swedish_source"]


def failure_taxonomy():
    return ["format_line_count", "format_bullet_marker", "format_too_long", "format_markdown", "wrong_language",
            "missing_number", "missing_entity", "missing_date", "nonanswer", "other"]


# ----------------------------------------------------------------------------------------------- formatting helpers


def fmt_number(n: int, lang: str) -> str:
    s = f"{n:,}"
    return s.replace(",", " ") if lang == "sv" else s


def fmt_date(d: dt.date, lang: str, style: str = "dmy") -> str:
    if lang == "sv":
        return f"{d.day} {MONTHS_SV[d.month - 1]} {d.year}"
    if style == "mdy":
        return f"{MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def fold(s: str) -> str:
    """Casefold, strip diacritics, unify whitespace (spec: name normalisation)."""
    s = entities.ascii_fold(s or "")
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.replace("’", "'")
    return re.sub(r"\s+", " ", s)


_NUM_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[,\u00a0\u202f\u2009 ]\d{3})+|\d+)((?:[.,]\d+)?)(?![\d])")


def extract_numbers(text: str) -> list[float]:
    """All numbers written with digits; thousands separators (comma, space, NBSP, thin space) removed."""
    out = []
    for m in _NUM_RE.finditer(text or ""):
        whole = re.sub(r"[,\u00a0\u202f\u2009 ]", "", m.group(1))
        frac = m.group(2)
        try:
            out.append(float(whole + ("." + frac[1:] if frac else "")))
        except ValueError:
            continue
    return out


_DATE_DMY = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({_MONTH_RE})\.?(?![a-z])(?:,?\s+(\d{{4}}))?",
                       re.IGNORECASE)
_DATE_MDY = re.compile(rf"(?<![a-z])({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?!\d)(?:,?\s+(\d{{4}}))?",
                       re.IGNORECASE)
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def extract_dates(text: str) -> list[tuple[int | None, int, int]]:
    """(year or None, month, day) for every recognised date expression (spec: date normalisation)."""
    t = unicodedata.normalize("NFKC", text or "").replace(" ", " ")
    out = []
    for m in _DATE_DMY.finditer(t):
        d, mo, y = int(m.group(1)), _MONTH_KEYS[m.group(2).lower()], m.group(3)
        if 1 <= d <= 31:
            out.append((int(y) if y else None, mo, d))
    for m in _DATE_MDY.finditer(t):
        mo, d, y = _MONTH_KEYS[m.group(1).lower()], int(m.group(2)), m.group(3)
        if 1 <= d <= 31:
            out.append((int(y) if y else None, mo, d))
    for m in _DATE_ISO.finditer(t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            out.append((y, mo, d))
    return out


def has_name(text: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(fold(name))}(?!\w)", fold(text)) is not None


def has_number(text: str, n: int) -> bool:
    return any(v == n for v in extract_numbers(text))


def has_date(text: str, ymd: list[int]) -> bool:
    y, m, d = ymd
    return any(mo == m and dd == d and (yy is None or yy == y) for yy, mo, dd in extract_dates(text))


def swedish_hits(text: str) -> set[str]:
    words = re.findall(r"[a-zåäö]+", (text or "").lower())
    return {w for w in words if w in SWEDISH_STOPWORDS}


# ----------------------------------------------------------------------------------------------- plan


def _rand_date(rng, start: dt.date, end: dt.date) -> dt.date:
    while True:
        d = start + dt.timedelta(days=rng.randrange((end - start).days + 1))
        if d.day <= 28:
            return d


def _rand_number(rng, lo: int, hi: int, avoid: set[int]) -> int:
    while True:
        n = rng.randint(lo, hi)
        if n > 1000 and rng.random() < 0.6:  # round-ish larger figures, as in real news
            n = round(n, -1) if n < 10000 else round(n, -2)
        if 2000 <= n <= 2100 or n in avoid or n < 1:
            continue
        return n


def plan(rng, slice, variant="main"):
    lang = "sv" if slice == "swedish_source" else "en"
    pool = "shift" if variant == "shift" else "main"
    comps = entities.companies(pool=pool)
    story_id = rng.choice(sorted(STORIES))
    st = STORIES[story_id]
    subj = rng.choice(comps)
    country = subj["country"]
    city = rng.choice(SWEDISH_CITIES if lang == "sv" else CITIES.get(country, CITIES["Sweden"]))
    sector = subj["sector"]
    facility = rng.choice(FACILITIES)
    date_style = "dmy" if lang == "sv" else rng.choice(["dmy", "mdy"])

    # key entity
    kind = st["ent"][0]
    if kind == "company":
        ent = rng.choice([c for c in comps if c["id"] != subj["id"]])["name"]
    elif kind == "person":
        ent = rng.choice(entities.people())["name"]
    else:
        ent = rng.choice(entities.products())["name"]
    fill = {"S": subj["name"], "sector": sector, "facility": facility, "city": city}

    # key number and date
    what, unit_en, unit_sv, lo, hi = st["num"]
    n = _rand_number(rng, max(lo, 40), hi, set())
    kd = _rand_date(rng, dt.date(2026, 12, 1), dt.date(2028, 6, 28))

    key = {
        "number": {"value": n, "text": fmt_number(n, lang), "unit": unit_sv if lang == "sv" else unit_en,
                   "what": what.format(**fill)},
        "entity": {"name": ent, "kind": kind, "role": st["ent"][1].format(**fill)},
        "date": {"ymd": [kd.year, kd.month, kd.day], "text": fmt_date(kd, lang, date_style),
                 "what": st["date"].format(**fill)},
    }

    # distractors
    used_people = {ent}
    used_nums = {n}
    used_dm = {(kd.month, kd.day)}
    distractors = []
    kinds = ["number", "number", "number"] if slice == "numbers_heavy" else ["name", "number", "date"]
    num_templates = rng.sample(DISTRACTOR_NUMBERS, 3)
    for i, k in enumerate(kinds):
        if k == "number":
            u_en, u_sv, dlo, dhi, ctx = num_templates[i]
            m = _rand_number(rng, dlo, dhi, used_nums)
            used_nums.add(m)
            distractors.append({"kind": "number", "value": m, "text": fmt_number(m, lang),
                                "unit": u_sv if lang == "sv" else u_en, "what": ctx})
        elif k == "name":
            while True:
                p = rng.choice(entities.people())["name"]
                if p not in used_people and p.split()[-1] not in ent:
                    break
            used_people.add(p)
            role, action = rng.choice(DISTRACTOR_ROLES)
            distractors.append({"kind": "name", "name": p, "role": role.format(**fill), "what": action})
        else:
            event, tense = rng.choice(DISTRACTOR_DATES)
            while True:
                if tense == "past":
                    d = _rand_date(rng, dt.date(2026, 2, 1), dt.date(2026, 11, 10))
                else:
                    d = _rand_date(rng, dt.date(2026, 12, 1), dt.date(2027, 10, 28))
                if (d.month, d.day) not in used_dm:
                    break
            used_dm.add((d.month, d.day))
            distractors.append({"kind": "date", "ymd": [d.year, d.month, d.day], "text": fmt_date(d, lang, date_style),
                                "what": event, "tense": tense})

    if variant == "shift":
        band = WORD_BANDS["shift"]
    elif slice == "long_articles":
        band = WORD_BANDS["long"]
    else:
        band = WORD_BANDS["main"]
    return {
        "lang": lang, "story": story_id, "about": st["about"].format(**fill), "subject": subj["name"],
        "city": city, "key": key, "distractors": distractors, "near_end": slice == "facts_near_end",
        "numbers_heavy": slice == "numbers_heavy", "words": list(band),
        "style": {"outlet": rng.choice(OUTLETS).format(sector=sector), "tone": rng.choice(TONES),
                  "opening": rng.choice(OPENINGS), "quotes": rng.choice(QUOTES),
                  "paragraphs": rng.randint(6, 9) if variant == "main" else rng.randint(12, 18)},
    }


# ----------------------------------------------------------------------------------------------- generate


def _anchor(f: dict) -> str:
    return f.get("text") or f.get("name")


def generator_prompt(plan):
    k = plan["key"]
    lang = "Swedish" if plan["lang"] == "sv" else "English"
    lo, hi = plan["words"][0], plan["words"][1]
    st = plan["style"]
    quotes = st["quotes"]
    has_name_distractor = any(d["kind"] == "name" for d in plan["distractors"])
    if not has_name_distractor and quotes != "use no direct quotes":
        quotes += " (attributed only to unnamed sources such as 'a spokesperson')"
    elif has_name_distractor:
        quotes += " (only the minor person listed below may be named; other speakers stay unnamed)"

    main = [
        f'1. THE FIGURE: {k["number"]["what"]} is "{k["number"]["text"]}" ({k["number"]["text"]} {k["number"]["unit"]}).',
        f'2. THE NAME: {k["entity"]["role"]} is "{k["entity"]["name"]}".',
        f'3. THE DATE: {k["date"]["what"]} is "{k["date"]["text"]}".',
    ]
    minor = []
    for i, d in enumerate(plan["distractors"]):
        letter = "abc"[i]
        if d["kind"] == "number":
            minor.append(f'{letter}. A minor figure: {d["what"]} is "{d["text"]}" ({d["text"]} {d["unit"]}).')
        elif d["kind"] == "name":
            minor.append(f'{letter}. A minor person: "{d["name"]}", {d["role"]}, who {d["what"]}.')
        else:
            tense = "took place" if d["tense"] == "past" else "is planned"
            minor.append(f'{letter}. A minor date: {d["what"]} {tense} on "{d["text"]}".')

    if plan["near_end"]:
        placement = (f'STRUCTURE: the article builds up to the news. The headline and the first half of the article '
                     f'must NOT contain "{k["number"]["text"]}", "{k["entity"]["name"]}" or "{k["date"]["text"]}". '
                     'The first half gives background, context and the minor details. The three main points are '
                     'revealed only in the final third of the article, and the text makes clear that they are the '
                     'real news. (You may hint at the news in the headline without giving these three items.)')
    else:
        placement = ('STRUCTURE: the three main points are the headline news. Put them in the headline and the opening '
                     'paragraphs, give them the most space, and come back to them later in the article. '
                     'A reader who remembers only three things should remember these three.')
    if plan["numbers_heavy"]:
        figures = (f'This is a figure-heavy article: besides the figures listed, add three to five further background '
                   f'figures (shares, counts, prices) in passing, all clearly secondary. None of them may equal '
                   f'{k["number"]["value"]}, and none may be another value for the main figure.')
    else:
        figures = ('Apart from the figures listed, avoid other specific numbers (years used as background are fine).')

    return f"""Write a news article in {lang} for {st['outlet']}.

Topic: {plan['about']}.
The article is written in mid-November 2026; do not state its publication date.
Length: between {lo} and {hi} words (the hard limits are {plan['words'][2]}-{plan['words'][3]} words), about {st['paragraphs']} paragraphs.
Style: {st['tone']}; {st['opening']}; {quotes}.

THE THREE MAIN POINTS (the most important facts of the article):
{chr(10).join(main)}

THREE MINOR DETAILS (mention each one once, in passing, in the middle of a paragraph; clearly less important than the main points; never in the headline or the first paragraph):
{chr(10).join(minor)}

{placement}

RULES:
- Every quoted string above must appear in the article exactly as written, character for character (same digits, digit separators, spelling, accents and capitalisation). Write each date in exactly the form given.
- Each main point has one value only: never give a second or conflicting figure, name or date for it, and never restate the main figure in another form (no rounding, no words, no other units).
- Do not name any other people, companies, organisations or products besides "{plan['subject']}" and the names listed above. Refer to anyone else generically ("a spokesperson", "local officials", "a supplier"). Real place names are fine.
- Do not include any other calendar dates (day and month) besides the ones listed.
- {figures}
- Plain text only: a headline on the first line, a blank line, then the paragraphs. No Markdown, no bold, no subheadings, no bullet points or lists.
- Output only the article."""


def make_input(plan, text):
    t = (text or "").replace(" ", " ").replace(" ", " ").replace(" ", " ").replace("\r\n", "\n")
    lines = []
    for line in t.split("\n"):
        line = re.sub(r"^\s*#+\s*", "", line).replace("**", "").replace("__", "")
        lines.append(line.rstrip())
    t = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def _find_number(text: str, s: str) -> int:
    m = re.search(rf"(?<![\d.,]){re.escape(s)}(?![\d]|[.,]\d)", text)
    return m.start() if m else -1


def _find_anchor(text: str, f: dict) -> int:
    if "value" in f:
        return _find_number(text, f["text"])
    if "ymd" in f:
        return text.find(f["text"])
    m = re.search(rf"(?<!\w){re.escape(f['name'])}(?!\w)", text)
    return m.start() if m else -1


def verify(plan, text):
    if not text or not text.strip():
        return False, "empty"
    words = len(text.split())
    lo, hi = plan["words"][2], plan["words"][3]
    if not lo <= words <= hi:
        return False, f"word count {words} outside {lo}-{hi}"
    for line in text.split("\n"):
        if re.match(r"^\s*([-*•]\s|\d+[.)]\s)", line):
            return False, "list or bullet line in article"
    k = plan["key"]
    facts = [("key " + n, k[n]) for n in ("number", "entity", "date")] + \
        [("distractor " + d["kind"], d) for d in plan["distractors"]]
    pos = {}
    for label, f in facts:
        p = _find_anchor(text, f)
        if p < 0:
            return False, f"{label} {_anchor(f)!r} missing"
        pos[label] = p
    planned = {(f["ymd"][1], f["ymd"][2]) for _, f in facts if "ymd" in f}
    extra = sorted({(m, d) for _, m, d in extract_dates(text)} - planned)
    if extra:
        return False, f"unplanned date(s) {extra}"
    if plan["near_end"]:
        half = len(text) / 2
        early = [lab for lab in ("key number", "key entity", "key date") if pos[lab] < half]
        if early:
            return False, f"near_end: {', '.join(early)} in first half"
    sv = len([w for w in re.findall(r"[a-zåäö]+", text.lower()) if w in SWEDISH_STOPWORDS])
    if plan["lang"] == "sv" and sv < 15:
        return False, "article does not look Swedish"
    if plan["lang"] == "en" and sv > 5:
        return False, "English article contains Swedish"
    return True, ""


def verifier_brief(plan):
    k = plan["key"]
    minor = "; ".join(f"{d['what']} ({_anchor(d)})" if d["kind"] != "name" else f"{d['name']}, {d['role']}"
                      for d in plan["distractors"])
    where = (" The three main points are deliberately revealed only near the end of the article (that is expected, "
             "not a problem)." if plan["near_end"] else "")
    return (f"A three-bullet summary of this article must cover its three main points: "
            f"(1) {k['number']['what']} = {k['number']['text']}; (2) {k['entity']['role']} = {k['entity']['name']}; "
            f"(3) {k['date']['what']} = {k['date']['text']}.{where} "
            f"Three minor details also appear and must be clearly less important: {minor}. "
            f"The answer changes if a main point is missing, is given a second or conflicting value, or is presented "
            f"only as a minor aside; if a minor detail (or any other figure, name or date) is presented as more "
            f"important than a main point; or if the article's real headline news is something other than these "
            f"three points. The article language is {'Swedish' if plan['lang'] == 'sv' else 'English'}.")


# ----------------------------------------------------------------------------------------------- label / score


def label(plan):
    k = plan["key"]
    return {"number": k["number"]["value"], "number_text": k["number"]["text"],
            "entity": k["entity"]["name"], "entity_kind": k["entity"]["kind"],
            "date": k["date"]["ymd"], "date_text": k["date"]["text"]}


def answer_strings(expected):
    return [s for s in (expected["entity"], expected["date_text"], expected["number_text"]) if len(s) >= 5]


def parse(output, settings, item):
    try:
        if isinstance(output, list):
            output = output[0] if output else {}
        output = output or {}
        return {"text": output.get("text") or "", "refusal": output.get("refusal")}
    except Exception:  # noqa: BLE001
        return {"text": "", "refusal": None}


_MD_PATTERNS = [
    (re.compile(r"\*\*|__|~~|`"), "bold/code/strike"),
    (re.compile(r"\[[^\]]*\]\([^)]*\)"), "link"),
    (re.compile(r"(?<![\w*])\*(?!\s)[^*\n]+(?<!\s)\*(?![\w*])"), "italic"),
    (re.compile(r"(?<!\w)_(?!\s)[^_\n]+(?<!\s)_(?!\w)"), "italic"),
    (re.compile(r"^\s*(#|>|[-*+•]\s|\d+[.)]\s)"), "nested marker"),
    (re.compile(r"</?[a-zA-Z][^>]*>"), "html"),
]


def check_format(text: str) -> dict:
    t = (text or "").strip()
    lines = t.splitlines() if t else []
    problems = []
    max_words = 0
    total_words = 0
    if len(lines) != 3:
        problems.append("format_line_count")
    bad_marker = markdown = too_long = False
    for line in lines:
        line = line.rstrip()
        if not line.startswith("- ") or not line[2:].strip():
            bad_marker = True
            content = re.sub(r"^\s*([-*+•]|\d+[.)])?\s*", "", line)
        else:
            content = line[2:]
            if any(p.search(content) for p, _ in _MD_PATTERNS):
                markdown = True
        if re.match(r"^\s*#", line) or "**" in line or "`" in line:
            markdown = True
        n = len([w for w in content.split() if re.search(r"\w", w)])
        max_words = max(max_words, n)
        total_words += n
        if n > 20:
            too_long = True
    if bad_marker:
        problems.append("format_bullet_marker")
    if too_long:
        problems.append("format_too_long")
    if markdown:
        problems.append("format_markdown")
    if len(swedish_hits(t)) >= 2:
        problems.append("wrong_language")
    return {"problems": problems, "lines": len(lines), "max_words": max_words, "total_words": total_words}


def score(expected, parsed):
    parsed = parsed if isinstance(parsed, dict) else {"text": str(parsed or ""), "refusal": None}
    text = parsed.get("text") or ""
    t = text.strip()
    has_bullet = any(line.startswith("- ") for line in t.splitlines())
    nonanswer = (not t) or bool(parsed.get("refusal")) or (not has_bullet and "?" in t)
    fmt = check_format(text)
    covered = {"number": has_number(t, expected["number"]), "entity": has_name(t, expected["entity"]),
               "date": has_date(t, expected["date"])}
    n_cov = sum(covered.values())
    format_ok = not fmt["problems"] and not nonanswer
    passed = format_ok and n_cov == 3
    cats = []
    if nonanswer:
        cats.append("nonanswer")
    else:
        cats += fmt["problems"]
        cats += [f"missing_{k}" for k, v in covered.items() if not v]
    diff = ""
    if not passed:
        parts = []
        if nonanswer:
            parts.append("nonanswer")
        if fmt["problems"]:
            parts.append(f"format: {','.join(fmt['problems'])} (lines={fmt['lines']}, max_words={fmt['max_words']})")
        miss = [f"{k}={expected['number_text'] if k == 'number' else expected['entity'] if k == 'entity' else expected['date_text']}"
                for k, v in covered.items() if not v]
        if miss:
            parts.append("missing " + "; ".join(miss))
        diff = " | ".join(parts)
    return {"passed": passed, "valid": format_ok, "nonanswer": nonanswer,
            "secondary": {"format_ok": int(format_ok), "facts_covered": n_cov, "lines": fmt["lines"],
                          "max_words": fmt["max_words"], "total_words": fmt["total_words"],
                          "number_covered": int(covered["number"]), "entity_covered": int(covered["entity"]),
                          "date_covered": int(covered["date"])},
            "categories": cats if not passed else [], "diff": diff}


def aggregate(rows):
    sec = [r.get("secondary") or {} for r in rows]
    sec = [s for s in sec if "format_ok" in s]
    if not sec:
        return {}
    n = len(sec)
    out = {k: sum(s[k] for s in sec) / n for k in ("format_ok", "facts_covered", "total_words", "number_covered",
                                                     "entity_covered", "date_covered")}
    out["over_20_words_rate"] = sum(1 for s in sec if s["max_words"] > 20) / n
    out["line_count_ok_rate"] = sum(1 for s in sec if s["lines"] == 3) / n
    return out


def legacy_markers():
    return [r"(?i)\bno headings\b", r"(?i)\bbe concise\b", r"\bEXACTLY\b", r"\bIMPORTANT\b", r"\bNEVER\b"]
