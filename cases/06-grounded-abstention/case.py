"""Case 06: grounded answers with abstention. See spec.md (single source of truth)."""
from __future__ import annotations

import re

from harness import entities
from harness.entities import ascii_fold

CASE_ID = "06"
NAME = "Grounded answers with abstention"

MAX_WORDS = 15
NF = "NOT_FOUND"

CITIES = ["Malmö", "Uppsala", "Lund", "Linköping", "Örebro", "Västerås", "Umeå", "Hamburg", "Leipzig", "Dresden",
          "Bremen", "Stuttgart", "Bonn", "Graz", "Basel", "Oslo", "Bergen", "Stavanger", "Tampere", "Turku",
          "Aarhus", "Odense", "Rotterdam", "Utrecht", "Lyon", "Lille", "Bordeaux", "Manchester", "Leeds", "Bristol",
          "Glasgow", "Austin", "Denver", "Boston", "Trondheim", "Gdansk"]

# attribute -> (entity type, numeric, (lo, hi) or value kind)
ATTRS = {
    "founded_year": ("company", True, (1948, 2018)),
    "employees": ("company", True, (120, 980)),
    "hq_city": ("company", False, "city"),
    "ceo": ("company", False, "person"),
    "flagship": ("company", False, "product"),
    "birth_year": ("person", True, (1956, 1995)),
    "birth_city": ("person", False, "city"),
    "employer": ("person", False, "company"),
    "launch_year": ("product", True, (2009, 2025)),
    "price": ("product", True, (19, 899)),
    "weight": ("product", True, (85, 950)),
    "manufacturer": ("product", False, "company"),
}

# fact phrasing for the generator (English instructions; the generator writes in the target language)
FACT = {
    "founded_year": "{e} was founded in {v}",
    "employees": "{e} has {v} employees",
    "hq_city": "{e} has its headquarters in {v}",
    "ceo": "the CEO of {e} is {v}",
    "flagship": "{e} is best known for its product {v}",
    "birth_year": "{e} was born in {v}",
    "birth_city": "{e} was born in the city of {v}",
    "employer": "{e} works for the company {v}",
    "launch_year": "{e} was launched in {v}",
    "price": "{e} costs {v} euros",
    "weight": "{e} weighs {v} grams",
    "manufacturer": "{e} is made by the company {v}",
}

# what the text must not reveal for an unanswerable item
ABSENT = {
    "founded_year": "when {e} was founded or how old it is (no founding year, no 'since <year>', no 'for N years')",
    "employees": "how many people work at {e} (no headcount, no staff numbers, no approximate size in employees)",
    "hq_city": "where {e} has its headquarters or is based (no city or country as its home, no '<city>-based')",
    "ceo": "who leads {e} (no CEO, managing director, founder-in-charge or other head named)",
    "flagship": "which product {e} is known for (name no products of {e})",
    "birth_year": "when {e} was born or how old they are",
    "birth_city": "where {e} was born or grew up",
    "employer": "which company or organisation {e} works for (no employer, no 'at <company>')",
    "launch_year": "when {e} was launched, released or introduced, or how long it has been on sale",
    "price": "what {e} costs (no price, no price range, no discount amounts)",
    "weight": "how much {e} weighs",
    "manufacturer": "which company makes, sells or develops {e}",
}

QUESTIONS = {
    "en": {
        "founded_year": "In what year was {e} founded?", "employees": "How many employees does {e} have?",
        "hq_city": "In which city does {e} have its headquarters?", "ceo": "Who is the CEO of {e}?",
        "flagship": "Which product is {e} best known for?", "birth_year": "In what year was {e} born?",
        "birth_city": "In which city was {e} born?", "employer": "Which company does {e} work for?",
        "launch_year": "In what year was {e} launched?", "price": "How much does {e} cost?",
        "weight": "How much does {e} weigh?", "manufacturer": "Which company makes {e}?",
    },
    "sv": {
        "founded_year": "Vilket år grundades {e}?", "employees": "Hur många anställda har {e}?",
        "hq_city": "I vilken stad har {e} sitt huvudkontor?", "ceo": "Vem är vd för {e}?",
        "flagship": "Vilken produkt är {e} mest känt för?", "birth_year": "Vilket år föddes {e}?",
        "birth_city": "I vilken stad föddes {e}?", "employer": "Vilket företag arbetar {e} på?",
        "launch_year": "Vilket år lanserades {e}?", "price": "Vad kostar {e}?",
        "weight": "Hur mycket väger {e}?", "manufacturer": "Vilket företag tillverkar {e}?",
    },
    "de": {
        "founded_year": "In welchem Jahr wurde {e} gegründet?", "employees": "Wie viele Mitarbeiter hat {e}?",
        "hq_city": "In welcher Stadt hat {e} seinen Hauptsitz?", "ceo": "Wer ist CEO von {e}?",
        "flagship": "Für welches Produkt ist {e} am bekanntesten?", "birth_year": "In welchem Jahr wurde {e} geboren?",
        "birth_city": "In welcher Stadt wurde {e} geboren?", "employer": "Für welches Unternehmen arbeitet {e}?",
        "launch_year": "In welchem Jahr kam {e} auf den Markt?", "price": "Wie viel kostet {e}?",
        "weight": "Wie viel wiegt {e}?", "manufacturer": "Welches Unternehmen stellt {e} her?",
    },
}
LANG_NAME = {"en": "English", "sv": "Swedish", "de": "German"}
LANG_HINT = {"en": [" the ", " and ", " of "], "sv": [" och ", " är ", " som ", " att ", " för "],
             "de": [" und ", " ist ", " der ", " die ", " das "]}

GENRES = ["news article", "press release", "company blog post", "trade magazine profile", "encyclopedia-style entry",
          "local newspaper feature", "investor newsletter excerpt", "third-person interview write-up",
          "industry report excerpt", "internal staff newsletter item", "conference recap", "podcast episode summary"]
ANGLES = ["a recent expansion", "sustainability work", "hiring and workplace culture", "a new partnership",
          "history and milestones", "market challenges", "a product update", "customer stories", "an award",
          "a leadership interview", "research and development", "a trade fair appearance"]
OPENINGS = ["open with a short quote", "open with a scene-setting sentence", "open directly with the main news",
            "open with a question to the reader", "open with a bit of background on the industry",
            "open with an anecdote"]
ROLES = ["engineer", "designer", "researcher", "sales director", "architect", "chef", "economist", "journalist",
         "product manager", "data scientist", "lawyer", "photographer"]
NO_WEIGHT = {"software", "service"}
EXCLUSIVE = {"birth_year", "birth_city"}  # both say "born in"; never a filler for each other

SLICES = ["plain", "lookalike_distractor", "numeric_answer", "answer_last_sentence", "answer_two_sentences",
          "unanswerable"]
VOWELS = "aeiou"


def slices():
    return list(SLICES)


def slice_weights(variant):
    return {"unanswerable": 35, "plain": 13, "lookalike_distractor": 13, "numeric_answer": 13,
            "answer_last_sentence": 13, "answer_two_sentences": 13}


# --------------------------------------------------------------------------- planning helpers

def _attrs_for(etype, category=None):
    out = [a for a, (t, _, _) in ATTRS.items() if t == etype]
    if etype == "product" and category in NO_WEIGHT:
        out.remove("weight")
    return out


def _vowel_mutations(name):
    """Names differing by one vowel (not the first letter; diacritic vowels and y count as vowels).

    Fallback for names with too few vowels: replace the last letter with a vowel."""
    out = []
    for i, ch in enumerate(name):
        if i == 0 or ascii_fold(ch).lower() not in VOWELS + "y":
            continue
        for v in VOWELS:
            if v == ascii_fold(ch).lower():
                continue
            out.append(name[:i] + v + name[i + 1:])
    if len(out) < 6:
        out += [name[:-1] + v for v in VOWELS if v != ascii_fold(name[-1]).lower()]
    return out


def _distinct(a, b):
    fa, fb = ascii_fold(a).lower(), ascii_fold(b).lower()
    return fa != fb and fa not in fb and fb not in fa


def _lookalike_names(rng, etype, name, k, taken):
    names = []
    if etype == "person":
        first, last = name.split(" ", 1)
        cands = [f"{f} {last}" for f in entities.FIRST if f != first]
        cands += [f"{first} {m}" for m in _vowel_mutations(last)]
    else:
        head, _, tail = name.partition(" ")
        cands = [m + (" " + tail if tail else "") for m in _vowel_mutations(head)]
    rng.shuffle(cands)
    for c in cands:
        if len(names) == k:
            break
        if all(_distinct(c, x) for x in [name, *names, *taken]):
            names.append(c)
    return names


def _sample_value(rng, attr, used, pools):
    _, numeric, spec = ATTRS[attr]
    for _ in range(1000):
        if numeric:
            v = str(rng.randint(*spec))
        elif spec == "city":
            v = rng.choice(CITIES)
        elif spec == "person":
            v = rng.choice(pools["people"])["name"]
        elif spec == "product":
            v = rng.choice(pools["products"])["name"]
        else:
            v = rng.choice(pools["companies"])["name"]
        if all(_distinct(v, u) for u in used) and not any(v in u or u in v for u in used):
            if numeric and any(u.isdigit() and abs(int(u) - int(v)) < 2 for u in used):
                continue
            return v
    raise RuntimeError("could not sample a distinct value")


def plan(rng, slice, variant="main"):
    pool = "shift" if variant == "shift" else "main"
    pools = {"companies": entities.companies(pool), "people": entities.people(), "products": entities.products()}
    r = rng.random()
    lang = "sv" if r < 0.2 else ("de" if r < 0.3 else "en")
    etype = rng.choices(["company", "person", "product"], weights=[50, 25, 25])[0]
    desc = {}
    if etype == "company":
        ent = rng.choice(pools["companies"])
        name = ent["name"]
        desc = {"sector": ent["sector"]}
    elif etype == "person":
        ent = rng.choice(pools["people"])
        name = ent["name"]
        desc = {"role": rng.choice(ROLES)}
    else:
        ent = rng.choice(pools["products"])
        name = ent["name"]
        desc = {"category": ent["category"]}
    attrs = _attrs_for(etype, desc.get("category"))
    numeric_attrs = [a for a in attrs if ATTRS[a][1]]
    text_attrs = [a for a in attrs if not ATTRS[a][1]]
    if slice == "numeric_answer":
        attr = rng.choice(numeric_attrs)
    elif rng.random() < 0.65:
        attr = rng.choice(text_attrs)
    else:
        attr = rng.choice(numeric_attrs)
    answerable = slice != "unanswerable"
    if variant == "shift":
        n_look = 2
        unans_kind = "lookalike" if not answerable else None
    elif slice == "lookalike_distractor":
        n_look, unans_kind = 1, None
    elif slice == "unanswerable":
        unans_kind = rng.choice(["missing", "lookalike"])
        n_look = 1 if unans_kind == "lookalike" else 0
    else:
        n_look, unans_kind = 0, None
    used = [name]
    value = _sample_value(rng, attr, used, pools)
    used.append(value)
    others = [a for a in attrs if a != attr and {a, attr} != EXCLUSIVE]
    rng.shuffle(others)
    fillers = []
    chosen = others[:2]
    if set(chosen) == EXCLUSIVE:
        chosen = chosen[:1]
    for a in chosen:
        v = _sample_value(rng, a, used, pools)
        used.append(v)
        fillers.append({"attr": a, "value": v})
    look_names = _lookalike_names(rng, etype, name, n_look, used)
    if len(look_names) < n_look:
        raise RuntimeError(f"no look-alike names for {name}")
    lookalikes = []
    for ln in look_names:
        used.append(ln)
        lv = _sample_value(rng, attr, used, pools)
        used.append(lv)
        lookalikes.append({"name": ln, "value": lv})
    placement = {"answer_last_sentence": "last", "answer_two_sentences": "two"}.get(slice, "any")
    lo, hi = (600, 1800) if variant == "shift" else (200, 600)
    return {
        "lang": lang, "etype": etype, "name": name, "desc": desc, "attr": attr, "numeric": ATTRS[attr][1],
        "question": QUESTIONS[lang][attr].format(e=name), "answerable": answerable,
        "value": value if answerable else None, "fillers": fillers, "lookalikes": lookalikes,
        "unans_kind": unans_kind, "placement": placement,
        "words": rng.choice(list(range(lo + 40, hi - 20, 20))), "length_bounds": [lo, hi],
        "genre": rng.choice(GENRES), "angle": rng.choice(ANGLES), "opening": rng.choice(OPENINGS),
    }


# --------------------------------------------------------------------------- generation

def _entity_desc(plan):
    d = plan["desc"]
    if plan["etype"] == "company":
        return f'a company called "{plan["name"]}" working in {d["sector"]}'
    if plan["etype"] == "person":
        return f'a person called "{plan["name"]}", who works as a {d["role"]}'
    return f'a {d["category"]} product called "{plan["name"]}"'


def _kind(plan):
    return {"company": "company", "person": "person", "product": "product"}[plan["etype"]]


def generator_prompt(plan):
    e = plan["name"]
    lang = LANG_NAME[plan["lang"]]
    art = "an" if plan["genre"][0] in "aeiou" else "a"
    lines = [f"Write {art} {plan['genre']} in {lang}, about {plan['words']} words long (it must be between "
             f"{plan['length_bounds'][0]} and {plan['length_bounds'][1]} words). It is about {_entity_desc(plan)}, "
             f"with a focus on {plan['angle']}; {plan['opening']}.", "",
             "Facts you must state, each exactly once and clearly. Copy every quoted string verbatim, "
             "keep numbers as digits exactly as given (no thousands separators, no rounding, no words):"]
    def fact(attr, ent, val):
        return "- " + FACT[attr].format(e=f'"{ent}"', v=f'"{val}"')

    if plan["answerable"]:
        lines.append(fact(plan["attr"], e, plan["value"]))
    for f in plan["fillers"]:
        lines.append(fact(f["attr"], e, f["value"]))
    for lk in plan["lookalikes"]:
        lines.append(fact(plan["attr"], lk["name"], lk["value"]))
    lines.append("")
    if plan["lookalikes"]:
        names = " and ".join(f'"{lk["name"]}"' for lk in plan["lookalikes"])
        lines.append(f"{names} {'is a' if len(plan['lookalikes']) == 1 else 'are'} different {_kind(plan)}"
                     f"{'' if len(plan['lookalikes']) == 1 else 's'}, unrelated to \"{e}\" despite the similar name "
                     f"(for example a competitor, a partner, a namesake or a colleague). Give each its own sentences; "
                     f"never attribute their facts to \"{e}\", never say the names are similar or confusing, and "
                     f"always write each name exactly as given.")
    if plan["answerable"]:
        lines.append(f"A reader asking \"{plan['question']}\" must find exactly one answer for \"{e}\": "
                     f"\"{plan['value']}\". Do not give any other or approximate value for this, not even a former, "
                     f"planned or estimated one.")
        if plan["placement"] == "last":
            lines.append(f"Placement: the fact with \"{plan['value']}\" must be the very last sentence of the text, "
                         f"and \"{plan['value']}\" must not appear anywhere else.")
        elif plan["placement"] == "two":
            lines.append(f"Placement: spread this fact over two consecutive sentences. The first names \"{e}\" "
                         f"(without the value); the next sentence gives \"{plan['value']}\" but refers to {e} only "
                         f"with a pronoun or a phrase like \"the {_kind(plan)}\" and does not contain the name "
                         f"\"{e}\" or any part of it.")
    else:
        lines.append(f"Important: the text must NOT reveal {ABSENT[plan['attr']].format(e=chr(34) + e + chr(34))}. "
                     f"A careful reader asking \"{plan['question']}\" must not be able to answer it from the text, "
                     f"not even indirectly or approximately.")
    lines += ["",
              f"Always write \"{e}\" exactly like that. Do not state this kind of fact ({plan['attr'].replace('_', ' ')}) "
              f"for any other {_kind(plan)} or for anyone else beyond what is listed above. Other invented names "
              "may appear in passing.",
              "Output plain prose paragraphs only: no title, no headings, no bullet points, no Markdown, no notes "
              "about these instructions."]
    return "\n".join(lines)


def make_input(plan, text):
    return text.strip()


def item_extras(plan):
    return {"question": plan["question"]}


def user_message(item, settings):
    return f"CONTEXT:\n{item['input']}\n\nQUESTION: {item['question']}"


# --------------------------------------------------------------------------- verification

SENT_SPLIT = re.compile(r"(?<=[.!?])[\"'”»)]*\s+")


def _sentences(text):
    return [s for s in SENT_SPLIT.split(text.strip()) if s.strip()]


def _count(text, v, numeric):
    if numeric:
        return len(re.findall(rf"(?<!\d){re.escape(v)}(?!\d)", text))
    return len(re.findall(rf"(?<!\w){re.escape(v)}(?!\w)", text))


def _name_parts(plan):
    n = plan["name"]
    if plan["etype"] == "person":
        return [n, n.split(" ", 1)[1]]
    return [n, n.split(" ")[0]]


def verify(plan, text):
    e = plan["name"]
    if _count(text, e, False) < 1:
        return False, "target name missing"
    nw = len(text.split())
    lo, hi = plan["length_bounds"]
    if not (lo - 30 <= nw <= hi + 100 + (200 if plan["variant"] == "shift" else 0)):
        return False, f"length {nw} words out of bounds"
    if re.search(r"(?m)^\s*(#|[-*•] |\d+\. )", text) or "**" in text or "`" in text:
        return False, "markdown or list"
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    if not any(h in low for h in LANG_HINT[plan["lang"]]):
        return False, "language check failed"
    for f in plan["fillers"]:
        if _count(text, f["value"], ATTRS[f["attr"]][1]) < 1:
            return False, f"filler value {f['value']!r} missing"
    for lk in plan["lookalikes"]:
        if _count(text, lk["name"], False) < 1:
            return False, f"look-alike {lk['name']!r} missing"
        c = _count(text, lk["value"], plan["numeric"])
        if c < 1 or (plan["numeric"] and c > 1):
            return False, f"look-alike value {lk['value']!r} count {c}"
    numeric = plan["numeric"]
    if numeric:  # every planned number exactly once
        for f in plan["fillers"]:
            if ATTRS[f["attr"]][1] and _count(text, f["value"], True) != 1:
                return False, f"filler number {f['value']} not exactly once"
    if not plan["answerable"]:
        return True, ""
    v = plan["value"]
    c = _count(text, v, numeric)
    if c < 1:
        return False, "answer value missing"
    if numeric and c != 1:
        return False, f"answer number appears {c} times"
    sents = _sentences(text)
    hits = [i for i, s in enumerate(sents) if _count(s, v, numeric)]
    if plan["placement"] == "last":
        if hits != [len(sents) - 1]:
            return False, f"value not only in the last sentence (sentences {hits} of {len(sents)})"
    elif plan["placement"] == "two":
        i = hits[0]
        if any(_count(sents[i], p, False) for p in _name_parts(plan)):
            return False, "value sentence names the entity"
        if i == 0 or not any(_count(s, p, False) for s in sents[max(0, i - 2):i] for p in _name_parts(plan)):
            return False, "entity not named in the preceding sentences"
    return True, ""


def verifier_brief(plan):
    e = plan["name"]
    q = plan["question"]
    looks = "; ".join(f'"{lk["name"]}" (a different {_kind(plan)}) has the value "{lk["value"]}"'
                      for lk in plan["lookalikes"])
    look_line = (f"Look-alike entities with similar names are planned on purpose: {looks}. These belong to the "
                 f"look-alikes only and are fine as long as the text clearly attributes them to the look-alike, "
                 f"not to \"{e}\".") if plan["lookalikes"] else "No look-alike entity is planned."
    if plan["answerable"]:
        return (f"Question: \"{q}\" (asked about exactly \"{e}\"). The correct answer is \"{plan['value']}\", "
                f"which the text must state for \"{e}\". {look_line} Other facts about \"{e}\" (different attributes) are planned and irrelevant. The answer changes (flag it) if the text gives "
                f"\"{e}\" a second or conflicting value for this question (including a former, approximate or "
                f"planned one), if \"{plan['value']}\" is attributed to a different entity, if it is unclear "
                f"whether the value belongs to \"{e}\", or if the text suggests \"{e}\" and a look-alike are the "
                f"same {_kind(plan)}.")
    return (f"Question: \"{q}\" (asked about exactly \"{e}\"). The correct answer is that the text does NOT "
            f"contain the answer for \"{e}\", so a reader must reply NOT_FOUND. {look_line} Other facts about \"{e}\" (a different attribute than the one asked) are planned and do not answer the question. Flag the text if it "
            f"states or lets a reader derive the answer for \"{e}\" in any way: directly, approximately, through "
            f"a phrase like 'since <year>' or 'for N years', through a pronoun or 'the {_kind(plan)}' that refers "
            f"to \"{e}\", or by implying that \"{e}\" and a look-alike are the same.")


def label(plan):
    return {"answerable": plan["answerable"], "value": plan["value"], "numeric": plan["numeric"],
            "conflicting": [lk["value"] for lk in plan["lookalikes"]]}


def answer_strings(expected):
    return [s for s in [expected.get("value"), *expected.get("conflicting", [])] if s]


# --------------------------------------------------------------------------- parse and score

ABSTAIN_RE = re.compile(
    r"not_found|not (mentioned|stated|specified|provided|given|included|available|found|contained)"
    r"|does(n't| not) (say|state|mention|contain|specify|include|provide)|no information|cannot be determined"
    r"|unknown|framgår inte|nämns inte|inte nämns|anges inte|saknas|ingen information"
    r"|nicht (erwähnt|angegeben|genannt|enthalten)|keine (angabe|information)|unbekannt", re.IGNORECASE)
MD_RE = re.compile(r"(?m)^\s*(#|[-*] |\d+\. )|\*\*|__|`")


def _norm(s):
    return " ".join(re.sub(r"[^0-9a-z]+", " ", ascii_fold(s).lower()).split())


def appears(value, answer):
    v = _norm(value)
    return bool(v) and f" {v} " in f" {_norm(answer)} "


def is_exact_nf(t):
    t = t.strip()
    if t.endswith("."):
        t = t[:-1]
    return t == NF


def parse(output, settings, item):
    if isinstance(output, list):
        output = output[0] if output else {}
    output = output or {}
    return {"text": (output.get("text") or "").strip(), "refusal": bool(output.get("refusal")),
            "status": output.get("status")}


def score(expected, parsed):
    parsed = parsed or {}
    t = (parsed.get("text") or "").strip()
    refusal = bool(parsed.get("refusal"))
    exact = is_exact_nf(t)
    words = len(t.split())
    md = bool(MD_RE.search(t))
    clarify = (not exact) and "?" in t
    has_nf = NF.lower() in t.lower()
    abstained = exact or bool(ABSTAIN_RE.search(t))
    empty = not t
    nonanswer = empty or refusal or clarify
    valid = exact or (not empty and not refusal and not clarify and not md and not has_nf and words <= MAX_WORDS)
    cats = []
    if expected["answerable"]:
        conf = [c for c in expected.get("conflicting", []) if appears(c, t)]
        hit = appears(expected["value"], t)
        passed = (not empty and not refusal and not clarify and not md and not has_nf and words <= MAX_WORDS
                  and hit and not conf)
        if not passed:
            if empty or refusal:
                cats.append("empty_or_refusal")
            elif clarify:
                cats.append("clarifying_question")
            elif abstained and not hit:
                cats.append("over_abstain")
            else:
                if md or has_nf:
                    cats.append("format")
                if words > MAX_WORDS:
                    cats.append("too_long")
                if conf:
                    cats.append("lookalike_confusion")
                if not hit and not conf:
                    cats.append("wrong_value")
        diff = "" if passed else f"expected {expected['value']!r} (<= {MAX_WORDS} words), got {t[:200]!r}"
    else:
        passed = exact
        if not passed:
            if empty or refusal:
                cats.append("empty_or_refusal")
            elif clarify:
                cats.append("clarifying_question")
            elif has_nf:
                cats.append("format")
            elif abstained:
                cats.append("abstain_wrong_format")
            else:
                cats.append("answered_unanswerable")
        diff = "" if passed else f"expected exactly {NF!r}, got {t[:200]!r}"
    return {"passed": passed, "valid": valid, "nonanswer": nonanswer and not passed,
            "secondary": {"unanswerable": int(not expected["answerable"]), "abstained": int(abstained),
                          "clarify": int(clarify), "words": words},
            "categories": cats, "diff": diff}


def aggregate(rows):
    sec = [r.get("secondary") or {} for r in rows]
    sec = [s for s in sec if "unanswerable" in s]
    unans = [s for s in sec if s["unanswerable"]]
    ans = [s for s in sec if not s["unanswerable"]]
    abst = [s for s in sec if s["abstained"]]
    tp = sum(1 for s in abst if s["unanswerable"])
    ans_rows = [r for r in rows if (r.get("secondary") or {}).get("unanswerable") == 0]
    un_rows = [r for r in rows if (r.get("secondary") or {}).get("unanswerable") == 1]

    def ratio(a, b):
        return a / b if b else None

    return {"abstention_precision": ratio(tp, len(abst)), "abstention_recall": ratio(tp, len(unans)),
            "over_abstention_rate": ratio(sum(s["abstained"] for s in ans), len(ans)),
            "clarification_rate": ratio(sum(s["clarify"] for s in sec), len(sec)),
            "answerable_accuracy": ratio(sum(r["passed"] for r in ans_rows), len(ans_rows)),
            "unanswerable_accuracy": ratio(sum(r["passed"] for r in un_rows), len(un_rows))}


def failure_taxonomy():
    return ["over_abstain", "answered_unanswerable", "abstain_wrong_format", "lookalike_confusion", "wrong_value",
            "too_long", "format", "clarifying_question", "empty_or_refusal", "other"]


def legacy_markers():
    return [r"NEVER guess", r"NEVER use (outside|external) knowledge", r"\bALWAYS\b", r"IMPORTANT",
            r"(?i)be concise", r"NOT_FOUND"]
