"""Case 08: terminology-locked translation (Swedish product description -> English plain text).

spec.md is the single source of truth; the glossary tables there are generated from GLOSSARY / EXTENSION
below (tests check that they agree).
"""
from __future__ import annotations

import re

from harness import entities

CASE_ID = "08"
NAME = "Terminology-locked translation"

# Reference length = Swedish source word count x LENGTH_RATIO (calibrated on pilot outputs, fixed before sealing).
LENGTH_RATIO = 1.15
LENGTH_BOUNDS = (0.8, 1.4)
SRC_WORDS = (80, 250)


def _t(sv, en, forbidden, pos, forms, compounds, avoid):
    return {"sv": sv, "en": en, "forbidden": list(forbidden), "pos": pos, "forms": list(forms),
            "compounds": [list(c) for c in compounds], "avoid": list(avoid)}


# avoid: Swedish patterns that must not occur in a source planning this term (their faithful translation would
# naturally use a forbidden alternative). Syntax: "word" = word-start prefix; "=word" = exact word; "~text" = substring.
GLOSSARY = [
    _t("laddare", "charger", ["adapter", "power supply"], "noun", ["laddaren", "laddarna"],
       [["snabbladdare", "fast charger"], ["billaddare", "car charger"]],
       ["~adapter", "~nätaggregat", "~strömförsörjning", "~nätdel"]),
    _t("batteri", "battery", ["accumulator", "power cell"], "noun", ["batteriet", "batterier", "batterierna"],
       [["batteritid", "battery life"], ["reservbatteri", "spare battery"]],
       ["~ackumulator", "=cell", "=cellen", "=celler"]),
    _t("skärm", "display", ["screen", "panel"], "noun", ["skärmen", "skärmar", "skärmarna"],
       [["skärmstorlek", "display size"], ["skärmyta", "display area"]],
       ["~bildskärm", "~pekskärm", "panel", "~monitor"]),
    _t("fodral", "case", ["pouch", "sleeve"], "noun", ["fodralet", "fodralen"],
       [["skyddsfodral", "protective case"], ["läderfodral", "leather case"]],
       ["påse", "~hylsa", "=ärm", "ärmar"]),
    _t("sladd", "cord", ["wire", "flex"], "noun", ["sladden", "sladdar", "sladdarna"],
       [["strömsladd", "power cord"], ["förlängningssladd", "extension cord"]],
       ["=tråd", "=tråden", "=trådar", "ledning"]),
    _t("kontakt", "plug", ["connector", "socket"], "noun", ["kontakten", "kontakter", "kontakterna"],
       [["stickkontakt", "plug"], ["USB-kontakt", "USB plug"]],
       ["~kontaktdon", "~uttag", "sockel", "koppling"]),
    _t("strömbrytare", "power switch", ["on/off switch", "toggle"], "noun", ["strömbrytaren", "strömbrytarna"],
       [["huvudströmbrytare", "main power switch"]],
       ["~på/av", "~av/på", "~vippbrytare", "~toggle"]),
    _t("knapp", "button", ["knob", "toggle"], "noun", ["knappen", "knappar", "knapparna"],
       [["strömknapp", "power button"], ["startknapp", "start button"]],
       ["vred", "=ratt", "=ratten", "=rattar", "~vippbrytare", "~toggle"]),
    _t("hölje", "housing", ["casing", "enclosure"], "noun", ["höljet", "höljen", "höljena"],
       [["aluminiumhölje", "aluminium housing"], ["plasthölje", "plastic housing"]],
       ["kåpa", "~inkapsl", "=skal", "=skalet", "~mobilskal"]),
    _t("lock", "lid", ["cap", "hatch"], "noun", ["locket", "locken"],
       [["glaslock", "glass lid"], ["skruvlock", "screw lid"]],
       ["~kapsyl", "kork", "~hätta", "lucka", "luckan", "~mössa"]),
    _t("fäste", "mount", ["bracket", "holder"], "noun", ["fästet", "fästen", "fästena"],
       [["väggfäste", "wall mount"], ["takfäste", "ceiling mount"]],
       ["~hållare", "konsol"]),
    _t("reglage", "control", ["slider", "dial"], "noun", ["reglaget", "reglagen"],
       [["volymreglage", "volume control"], ["temperaturreglage", "temperature control"]],
       ["~skjutreglage", "vred", "=ratt", "=ratten", "=rattar", "~skjutknapp"]),
    _t("sil", "strainer", ["sieve", "colander"], "noun", ["silen", "silar", "silarna"],
       [["tesil", "tea strainer"], ["kaffesil", "coffee strainer"]],
       ["~durkslag", "såll"]),
    _t("behållare", "container", ["tank", "reservoir"], "noun", ["behållaren", "behållarna"],
       [["vattenbehållare", "water container"], ["förvaringsbehållare", "storage container"]],
       ["~tank", "~reservoar"]),
    _t("munstycke", "nozzle", ["spout", "jet"], "noun", ["munstycket", "munstycken", "munstyckena"],
       [["sprutmunstycke", "spray nozzle"], ["ångmunstycke", "steam nozzle"]],
       ["=pip", "=pipen", "~stråle", "=jet"]),
    _t("slang", "hose", ["tube", "pipe"], "noun", ["slangen", "slangar", "slangarna"],
       [["trädgårdsslang", "garden hose"], ["vattenslang", "water hose"]],
       ["=tub", "=tuben", "=tuber", "=rör", "=röret", "~rörledning", "=pipa", "=pipan"]),
    _t("handtag", "handle", ["grip", "hilt"], "noun", ["handtaget", "handtagen"],
       [["bärhandtag", "carrying handle"], ["gummihandtag", "rubber handle"]],
       ["~grepp", "fattning", "skaft"]),
    _t("givare", "sensor", ["detector", "probe"], "noun", ["givaren", "givarna"],
       [["temperaturgivare", "temperature sensor"], ["rörelsegivare", "motion sensor"]],
       ["~detektor", "sond"]),
    _t("mätare", "gauge", ["indicator", "readout"], "noun", ["mätaren", "mätarna"],
       [["tryckmätare", "pressure gauge"], ["nivåmätare", "level gauge"]],
       ["~indikator", "avläsning"]),
    _t("vattentät", "waterproof", ["water-resistant", "watertight"], "adj", ["vattentäta", "vattentätt"], [],
       ["~vattenbeständ", "~vattenresistent", "=tät", "=täta", "=tätt"]),
    _t("tålig", "durable", ["robust", "sturdy"], "adj", ["tåliga", "tåligt"], [],
       ["robust", "stadig"]),
    _t("slitstark", "hard-wearing", ["wear-resistant", "long-lasting"], "adj", ["slitstarka", "slitstarkt"], [],
       ["~långvarig", "~långlivad", "~hållbar", "~slitstyrk", "~slittålig", "~håller länge", "~räcker länge"]),
    _t("trådlös", "wireless", ["cordless", "cable-free"], "adj", ["trådlösa", "trådlöst"], [],
       ["~sladdlös", "~kabelfri", "~utan sladd", "~utan kabel"]),
    _t("uppladdningsbar", "rechargeable", ["chargeable", "reusable"], "adj",
       ["uppladdningsbara", "uppladdningsbart"], [],
       ["~återanvänd", "laddningsbar", "laddbar"]),
    _t("inställning", "setting", ["configuration", "preset"], "noun",
       ["inställningen", "inställningar", "inställningarna"],
       [["värmeinställning", "heat setting"], ["hastighetsinställning", "speed setting"]],
       ["~konfigur", "~förinställ"]),
    _t("läge", "mode", ["position", "program"], "noun", ["läget", "lägen", "lägena"],
       [["nattläge", "night mode"], ["viloläge", "sleep mode"]],
       ["position", "program", "placer"]),
    _t("tillbehör", "accessory", ["add-on", "attachment"], "noun", ["tillbehöret", "tillbehören"],
       [["extratillbehör", "extra accessory"], ["originaltillbehör", "original accessory"]],
       ["~tillsats", "tillägg", "påbyggnad"]),
    _t("reservdel", "spare part", ["replacement part", "component"], "noun",
       ["reservdelen", "reservdelar", "reservdelarna"], [],
       ["~komponent", "~ersättningsdel", "~utbytesdel"]),
    _t("garanti", "warranty", ["guarantee", "guaranty"], "noun", ["garantin", "garantier", "garantierna"],
       [["garantitid", "warranty period"], ["produktgaranti", "product warranty"]],
       ["~garanter", "~nöjd-kund", "~nöjdkund"]),
    _t("bruksanvisning", "user manual", ["instructions", "guide"], "noun",
       ["bruksanvisningen", "bruksanvisningar"], [],
       ["~instruktion", "guid", "~handbok", "anvisning", "~vägled", "manual"]),
    _t("leverans", "delivery", ["shipment", "shipping"], "noun", ["leveransen", "leveranser", "leveranserna"],
       [["leveranstid", "delivery time"], ["hemleverans", "home delivery"]],
       ["~frakt", "skeppa", "sändning", "~försändelse", "skicka"]),
    _t("förpackning", "packaging", ["package", "box"], "noun", ["förpackningen"],
       [["originalförpackning", "original packaging"], ["presentförpackning", "gift packaging"]],
       ["~paket", "=låda", "=lådan", "=lådor", "~kartong", "=ask", "=asken", "förpacka"]),
    _t("vikt", "weight", ["mass", "heft"], "noun", ["vikten"],
       [["totalvikt", "total weight"], ["nettovikt", "net weight"]],
       ["massa", "tyngd"]),
    _t("mått", "dimensions", ["measurements", "proportions"], "noun", ["måtten"], [],
       ["~mätning", "proportion"]),
    _t("motor", "motor", ["engine", "drive unit"], "noun", ["motorn", "motorer", "motorerna"],
       [["elmotor", "electric motor"]],
       ["~drivenhet", "drivlina"]),
    _t("fläkt", "fan", ["blower", "ventilator"], "noun", ["fläkten", "fläktar", "fläktarna"],
       [["takfläkt", "ceiling fan"], ["kylfläkt", "cooling fan"]],
       ["~ventilator", "blås", "~lövblås"]),
    _t("lampa", "lamp", ["bulb", "luminaire"], "noun", ["lampan", "lampor", "lamporna"],
       [["bordslampa", "table lamp"], ["läslampa", "reading lamp"]],
       ["~glödlamp", "pära", "~armatur"]),
    _t("ljusstyrka", "brightness", ["luminosity", "luminance"], "noun", ["ljusstyrkan"], [],
       ["~lumin"]),
    _t("upplösning", "resolution", ["definition", "sharpness"], "noun", ["upplösningen", "upplösningar"],
       [["bildupplösning", "image resolution"], ["videoupplösning", "video resolution"]],
       ["~skärp", "~definition"]),
    _t("anslutning", "connection", ["port", "interface"], "noun", ["anslutningen", "anslutningar"],
       [["nätverksanslutning", "network connection"], ["USB-anslutning", "USB connection"]],
       ["=port", "=porten", "=portar", "=portarna", "~gränssnitt", "~uttag"]),
]

EXTENSION = [
    _t("termos", "vacuum flask", ["thermos", "bottle"], "noun", ["termosen", "termosar"],
       [["kaffetermos", "coffee vacuum flask"]], ["~flask"]),
    _t("kastrull", "saucepan", ["pot", "casserole"], "noun", ["kastrullen", "kastruller"],
       [["mjölkkastrull", "milk saucepan"]], ["gryt", "kruka", "krukan"]),
    _t("stekpanna", "frying pan", ["skillet", "frypan"], "noun", ["stekpannan", "stekpannor"],
       [["gjutjärnsstekpanna", "cast-iron frying pan"]], ["=panna", "=pannan", "=pannor"]),
    _t("skärbräda", "chopping board", ["cutting board", "carving board"], "noun", ["skärbrädan", "skärbrädor"], [],
       ["=bräda", "=brädan", "=brädor", "underlägg"]),
    _t("visp", "whisk", ["beater", "mixer"], "noun", ["vispen", "vispar"],
       [["ballongvisp", "balloon whisk"]], ["~mixer", "mixa", "~elvisp", "vispare"]),
    _t("lucka", "door", ["hatch", "flap"], "noun", ["luckan", "luckor"],
       [["ugnslucka", "oven door"], ["glaslucka", "glass door"]], ["~klaff"]),
    _t("galler", "grate", ["grill", "grid"], "noun", ["gallret"],
       [["ugnsgaller", "oven grate"], ["skyddsgaller", "protective grate"]], ["~grill", "rutnät"]),
    _t("ugnsvante", "oven glove", ["oven mitt", "kitchen glove"], "noun", ["ugnsvanten", "ugnsvantar"], [],
       ["~grytlapp", "=vante", "=vantar"]),
    _t("gräsklippare", "lawn mower", ["grass cutter", "grass trimmer"], "noun", ["gräsklipparen"],
       [["robotgräsklippare", "robotic lawn mower"]], ["~trimmer", "~grästrimm"]),
    _t("sekatör", "pruning shears", ["secateurs", "pruners"], "noun", ["sekatören", "sekatörer"], [],
       ["~beskärningssax"]),
    _t("vattenkanna", "watering can", ["water jug", "sprinkling can"], "noun", ["vattenkannan", "vattenkannor"], [],
       ["=kanna", "=kannan", "=kannor", "krus"]),
    _t("tältpinne", "tent peg", ["tent stake", "spike"], "noun", ["tältpinnen", "tältpinnar"], [],
       ["spik", "~jordspett"]),
    _t("sovsäck", "sleeping bag", ["bedroll", "sleep sack"], "noun", ["sovsäcken", "sovsäckar"],
       [["dunsovsäck", "down sleeping bag"]], ["~rullmadrass"]),
    _t("ryggsäck", "backpack", ["rucksack", "knapsack"], "noun", ["ryggsäcken", "ryggsäckar"],
       [["vandringsryggsäck", "hiking backpack"]], ["ränsel"]),
    _t("pannlampa", "head torch", ["headlamp", "headlight"], "noun", ["pannlampan", "pannlampor"], [],
       ["~strålkastar"]),
    _t("dragkedja", "zip", ["zipper", "slide fastener"], "noun", ["dragkedjan", "dragkedjor"],
       [["tvåvägsdragkedja", "two-way zip"]], ["~blixtlås"]),
    _t("spänne", "buckle", ["clasp", "clip"], "noun", ["spännet", "spännen"],
       [["bältesspänne", "belt buckle"], ["snabbspänne", "quick-release buckle"]],
       ["knäpp", "clips", "klämm"]),
    _t("sula", "sole", ["outsole", "tread"], "noun", ["sulan", "sulor"],
       [["gummisula", "rubber sole"]], ["~slitbana", "~yttersula", "mönster"]),
    _t("foder", "lining", ["liner", "inner layer"], "noun", ["fodret"],
       [["fleecefoder", "fleece lining"], ["ullfoder", "wool lining"]], ["~innerlager"]),
    _t("luva", "hood", ["cap", "cowl"], "noun", ["luvan", "luvor"], [],
       ["~mössa", "keps", "~hätta"]),
]

ALL_TERMS = GLOSSARY + EXTENSION
BY_SV = {t["sv"]: t for t in ALL_TERMS}
EXT_SV = {t["sv"] for t in EXTENSION}

GENERIC = ["garanti", "leverans", "förpackning", "tillbehör", "reservdel", "bruksanvisning", "vikt", "mått",
           "tålig", "slitstark", "vattentät"]
DOMAINS = {
    "electronics": {"terms": ["laddare", "batteri", "skärm", "fodral", "sladd", "kontakt", "strömbrytare", "knapp",
                              "trådlös", "uppladdningsbar", "inställning", "läge", "ljusstyrka", "upplösning",
                              "anslutning", "givare"],
                    "products": ["wireless earbuds", "portable speaker", "smartwatch", "tablet", "e-reader",
                                 "action camera", "baby monitor", "dashcam", "gaming controller", "video doorbell"]},
    "kitchen": {"terms": ["behållare", "munstycke", "lock", "sil", "reglage", "hölje", "motor", "inställning", "läge",
                          "sladd", "strömbrytare", "knapp", "handtag", "mätare", "kontakt"],
                "products": ["espresso machine", "electric kettle", "food processor", "air fryer", "juicer",
                             "coffee grinder", "milk frother", "soup maker", "rice cooker"]},
    "garden": {"terms": ["slang", "munstycke", "handtag", "behållare", "motor", "sladd", "mätare", "reglage", "fäste",
                         "kontakt", "strömbrytare", "batteri", "uppladdningsbar"],
               "products": ["pressure washer", "garden pump", "drip irrigation kit", "pond pump", "garden sprayer",
                            "wet-and-dry vacuum cleaner"]},
    "home": {"terms": ["lampa", "ljusstyrka", "fläkt", "fäste", "reglage", "strömbrytare", "sladd", "kontakt", "läge",
                       "motor", "hölje", "trådlös", "givare", "inställning", "knapp"],
             "products": ["desk lamp", "floor lamp", "ceiling fan", "pedestal fan", "air purifier", "dehumidifier",
                          "bedside lamp"]},
}
SHIFT_DOMAINS = {
    "kitchenware": {"terms": ["termos", "kastrull", "stekpanna", "skärbräda", "visp", "lucka", "galler", "ugnsvante"],
                    "products": ["cookware set", "kitchen starter kit", "baking set", "compact oven",
                                 "cabin kitchen kit"]},
    "garden_tools": {"terms": ["gräsklippare", "sekatör", "vattenkanna"],
                     "products": ["garden tool set", "allotment starter kit", "garden care bundle"]},
    "outdoor": {"terms": ["tältpinne", "sovsäck", "ryggsäck", "pannlampa", "dragkedja", "spänne", "sula", "foder",
                          "luva"],
                "products": ["camping kit", "hiking bundle", "winter jacket", "trekking set",
                             "festival camping pack"]},
}

STYLES = ["a friendly, persuasive web-shop product page", "a concise technical catalogue entry",
          "an enthusiastic launch announcement from the brand", "a calm, minimalist Scandinavian brand voice",
          "a retailer description written for first-time buyers", "a factual, spec-focused text for professionals",
          "a warm text that addresses the reader as 'du'", "a neutral, informative product sheet in full sentences"]
OPENINGS = ["Start with the product name.", "Start with an everyday situation where the product helps.",
            "Start with the product's main benefit.", "Start with the brand name and what it is known for."]
LENGTHS = [(85, 120), (110, 160), (150, 200), (190, 235)]

FORM_DESC = {"lemma": "exactly this base form", "form": "exactly this inflected form",
             "compound": "inside this compound word, written as one word (a Swedish ending may follow it)",
             "list": "in its base form, as one item of the comma-separated enumeration described below",
             "twice": "at least twice, in two different sentences (base or inflected forms)"}


# --------------------------------------------------------------------------- helpers

def word_count(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", text or ""))


def _avoid_regex(a: str) -> str:
    if a.startswith("="):
        return r"(?<!\w)" + re.escape(a[1:]) + r"(?!\w)"
    if a.startswith("~"):
        return re.escape(a[1:])
    return r"(?<!\w)" + re.escape(a)


def avoid_hits(term: dict, text: str) -> list[str]:
    return [a.lstrip("=~") for a in term["avoid"] if re.search(_avoid_regex(a), text, flags=re.IGNORECASE)]


def sv_strings(term: dict) -> list[str]:
    return [term["sv"], *term["forms"], *[c[0] for c in term["compounds"]]]


def _word_re(w: str) -> str:
    return r"(?<!\w)" + re.escape(w) + r"(?!\w)"


def sv_occurrences(term: dict, text: str) -> int:
    pat = "|".join(_word_re(w) for w in sorted([term["sv"], *term["forms"]], key=len, reverse=True))
    return len(re.findall(pat, text, flags=re.IGNORECASE))


def norm_en(text: str) -> str:
    t = (text or "").lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"[-‐‑‒–—]", " ", t)
    return re.sub(r"\s+", " ", t)


def en_variants(phrase: str) -> list[str]:
    words = norm_en(phrase).split()
    last = words[-1]
    forms = {last, last + "s", last + "es"}
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        forms.add(last[:-1] + "ies")
    if last.endswith("s"):
        forms.add(last[:-1])
    return sorted(" ".join(words[:-1] + [f]) for f in forms)


def en_regex(phrase: str) -> str:
    alts = []
    for v in sorted(en_variants(phrase), key=len, reverse=True):
        alts.append(r"\s+".join(re.escape(w) for w in v.split()))
    return r"(?<![\w])(?:" + "|".join(alts) + r")(?![\w])"


def en_count(phrase: str, text: str) -> int:
    return len(re.findall(en_regex(phrase), norm_en(text)))


def compatible(a: dict, b: dict) -> bool:
    """Two terms may share an item: neither's avoid patterns hit the other's Swedish strings and neither's
    forbidden alternatives occur inside the other's required rendering."""
    for x, y in ((a, b), (b, a)):
        if any(avoid_hits(x, s) for s in sv_strings(y)):
            return False
        if any(en_count(f, y["en"]) for f in x["forbidden"]):
            return False
    return True


# --------------------------------------------------------------------------- interface

def slices():
    return ["plain", "inflected_forms", "compound_words", "terms_in_lists", "terms_used_twice"]


def _eligible(sv: str, sl: str) -> bool:
    t = BY_SV[sv]
    return {"plain": True, "terms_used_twice": True, "inflected_forms": bool(t["forms"]),
            "compound_words": bool(t["compounds"]), "terms_in_lists": t["pos"] == "noun"}[sl]


def _entity_ok(name: str, terms: list[dict]) -> bool:
    return not any(avoid_hits(t, name) for t in terms) and not any(
        re.search(_word_re(s), name, flags=re.IGNORECASE) for t in terms for s in sv_strings(t))


def plan(rng, slice, variant="main"):
    n_special = {"plain": (0, 0), "inflected_forms": (2, 3), "compound_words": (1, 2), "terms_in_lists": (3, 4),
                 "terms_used_twice": (1, 2)}[slice]
    domains = DOMAINS if variant == "main" else SHIFT_DOMAINS
    for _ in range(200):
        dname = rng.choice(sorted(domains))
        dom = domains[dname]
        if variant == "main":
            k = rng.randint(3, 8)
            n_gen = rng.randint(1, min(3, k - 2))
            core_pool = [s for s in dom["terms"] if s not in GENERIC]
            n_core = k - n_gen
            extra_pool, n_extra = list(GENERIC), n_gen
        else:
            n_core = rng.randint(3, min(6, len(dom["terms"])))
            core_pool = list(dom["terms"])
            extra_pool, n_extra = list(GENERIC), rng.randint(0, 2)
        n_sp = rng.randint(*n_special)
        sp_pool = [s for s in core_pool if _eligible(s, slice)]
        if slice == "terms_in_lists" and variant == "main":  # list items may also be generic nouns
            sp_pool += [s for s in extra_pool if _eligible(s, slice)]
        rng.shuffle(sp_pool)
        chosen: list[str] = []
        for s in sp_pool:
            if len(chosen) == n_sp:
                break
            if all(compatible(BY_SV[s], BY_SV[c]) for c in chosen):
                chosen.append(s)
        if len(chosen) < n_sp:
            continue
        specials = list(chosen)
        n_core_left = n_core - sum(1 for s in chosen if s in core_pool)
        n_extra_left = n_extra - sum(1 for s in chosen if s in extra_pool)
        if n_core_left < 0 or n_extra_left < 0:
            continue
        for pool, n in ((core_pool, n_core_left), (extra_pool, n_extra_left)):
            pool = [s for s in pool if s not in chosen]
            rng.shuffle(pool)
            got = 0
            for s in pool:
                if got == n:
                    break
                if all(compatible(BY_SV[s], BY_SV[c]) for c in chosen):
                    chosen.append(s)
                    got += 1
        if not (3 <= len(chosen) <= 8):
            continue
        terms_full = [BY_SV[s] for s in chosen]
        companies = [c for c in entities.companies("main" if variant == "main" else "shift") if " " not in c["name"]]
        brand = product = None
        for _ in range(50):
            b = rng.choice(companies)["name"]
            p = rng.choice(entities.products())["name"]
            if b != p and _entity_ok(b, terms_full) and _entity_ok(p, terms_full):
                brand, product = b, p
                break
        if not brand:
            continue
        terms = []
        for s in chosen:
            t = BY_SV[s]
            mode, surface, min_count = "lemma", t["sv"], 1
            if s in specials:
                if slice == "inflected_forms":
                    mode, surface = "form", rng.choice(t["forms"])
                elif slice == "compound_words":
                    mode, surface = "compound", rng.choice(t["compounds"])[0]
                elif slice == "terms_in_lists":
                    mode = "list"
                elif slice == "terms_used_twice":
                    mode, min_count = "twice", 2
            terms.append({"sv": s, "glossary": "extension" if s in EXT_SV else "main", "mode": mode,
                          "surface": surface, "min_count": min_count})
        rng.shuffle(terms)
        return {"domain": dname, "product_type": rng.choice(dom["products"]), "brand": brand, "product": product,
                "style": rng.choice(STYLES), "opening": rng.choice(OPENINGS), "paragraphs": rng.randint(1, 3),
                "length": list(rng.choice(LENGTHS)), "terms": terms}
    raise RuntimeError(f"could not plan {slice}/{variant}")


def generator_prompt(plan):
    lines = []
    list_terms = [t["surface"] for t in plan["terms"] if t["mode"] == "list"]
    for t in plan["terms"]:
        g = BY_SV[t["sv"]]
        lines.append(f'- "{t["surface"]}" (meaning: {g["en"]}) - {FORM_DESC[t["mode"]]}'
                     + (f'; forms you may use: {", ".join([g["sv"], *g["forms"]])}' if t["mode"] == "twice" else ""))
    avoid_sv = sorted({a.lstrip("=~") for t in plan["terms"] for a in BY_SV[t["sv"]]["avoid"]})
    avoid_en = sorted({f for t in plan["terms"] for f in BY_SV[t["sv"]]["forbidden"]})
    lo, hi = plan["length"]
    parts = [
        f"Write a product description in Swedish (natural, idiomatic Swedish as on a Swedish retailer's website) "
        f"for the {plan['product_type']} \"{plan['product']}\" from the brand \"{plan['brand']}\".",
        f"Style: {plan['style']}. {plan['opening']} Use {plan['paragraphs']} paragraph(s) of running prose.",
        f"Length: between {lo} and {hi} words (hard limits: at least 80 and at most 250 words).",
        "",
        "The text MUST contain each of these Swedish words, used in the meaning given (the meaning is for you only; "
        "never write English):",
        *lines,
    ]
    if list_terms:
        parts += ["", "Include exactly one sentence with a comma-separated enumeration (for example after 'I köpet ingår' or "
                  "'Du får'), containing these words in their base form as list items: "
                  + ", ".join(f'"{s}"' for s in list_terms) + ". Write the enumeration inline in the sentence, "
                  "not as a bulleted or line-by-line list."]
    parts += [
        "",
        "Rules:",
        f"- Mention the names \"{plan['brand']}\" and \"{plan['product']}\" exactly as written; no other brands, "
        "products or company names.",
        "- Do not use these Swedish words or words built on them: " + ", ".join(avoid_sv) + ".",
        "- Avoid any wording whose natural English translation would be one of: " + ", ".join(avoid_en) + ".",
        "- Plain text only: no title line, no headings, no bullet points, no numbered lists, no Markdown, "
        "no emojis, no English words except the names.",
        "- Output only the Swedish product description, nothing else.",
    ]
    return "\n".join(parts)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


MD_SRC = re.compile(r"^\s*(#{1,6}\s|[-*+•]\s|\d+[.)]\s|>)|\*\*|__|`", re.MULTILINE)


def make_input(plan, text):
    return (text or "").strip()


def verify(plan, text):
    if not text:
        return False, "empty"
    n = word_count(text)
    if not SRC_WORDS[0] <= n <= SRC_WORDS[1]:
        return False, f"source has {n} words (allowed {SRC_WORDS[0]}-{SRC_WORDS[1]})"
    if MD_SRC.search(text):
        return False, "markdown or list formatting in source"
    for name in (plan["brand"], plan["product"]):
        if name not in text:
            return False, f"name {name!r} missing"
    for t in plan["terms"]:
        g = BY_SV[t["sv"]]
        if t["mode"] in ("lemma", "form", "list"):
            if not re.search(_word_re(t["surface"]), text, flags=re.IGNORECASE):
                return False, f"{t['surface']!r} missing"
        elif t["mode"] == "compound":
            if not re.search(r"(?<!\w)" + re.escape(t["surface"]), text, flags=re.IGNORECASE):
                return False, f"compound {t['surface']!r} missing"
        elif t["mode"] == "twice":
            if sv_occurrences(g, text) < 2:
                return False, f"{t['sv']!r} not used twice"
        hits = avoid_hits(g, text)
        if hits:
            return False, f"avoid word for {t['sv']!r}: {hits}"
    list_terms = [t["surface"] for t in plan["terms"] if t["mode"] == "list"]
    if list_terms:
        ok = any(all(re.search(_word_re(s), sent, flags=re.IGNORECASE) for s in list_terms)
                 and sent.count(",") >= len(list_terms) - 2 for sent in _sentences(text))
        if not ok:
            return False, "list terms not in one comma-separated enumeration"
    return True, ""


def verifier_brief(plan):
    rows = []
    for t in plan["terms"]:
        g = BY_SV[t["sv"]]
        rows.append(f'- Swedish "{t["surface"]}" must be translated as "{g["en"]}" (meaning: {g["en"]}); '
                    f'a translator must NOT need the English words: {", ".join(g["forbidden"])}')
    return (
        "The TEXT is a Swedish product description that will be translated into English. The scored answer is "
        "that the English translation uses these renderings:\n" + "\n".join(rows) + "\n"
        "The answer changes if: one of these Swedish words is missing or used in a different meaning (for "
        "example 'kontakt' meaning 'contact', 'knapp' meaning 'scarce', 'läge' meaning 'location'), so the "
        "listed English rendering would be a wrong translation; or other wording in the text would naturally "
        "be translated with one of the forbidden English words listed above; or the text is not Swedish prose. "
        "Other glossary-like words, style, length and product details do not matter.")


def item_extras(plan):
    if plan.get("variant") == "shift" or any(t["glossary"] == "extension" for t in plan["terms"]):
        return {"context": extension_glossary_text()}
    return {}


def extension_glossary_text() -> str:
    lines = [f"- {t['sv']} -> {t['en']} (NEVER: {', '.join(t['forbidden'])})" for t in EXTENSION]
    return "Additional glossary (mandatory for this text, same rules as the main glossary):\n" + "\n".join(lines)


def label(plan):
    return {"terms": [{"sv": t["sv"], "en": BY_SV[t["sv"]]["en"], "forbidden": BY_SV[t["sv"]]["forbidden"],
                       "min_count": t["min_count"]} for t in plan["terms"]],
            "length_ratio": LENGTH_RATIO, "length_bounds": list(LENGTH_BOUNDS)}


def parse(output, settings, item):
    try:
        out = output[0] if isinstance(output, list) else output
        out = out or {}
        return {"text": out.get("text") or "", "refusal": out.get("refusal"), "status": out.get("status"),
                "src_words": word_count((item or {}).get("input") or "")}
    except Exception:  # noqa: BLE001
        return {"text": "", "refusal": None, "status": None, "src_words": 0}


MD_OUT = re.compile(r"^\s*(#{1,6}\s|[-*+•]\s|\d+[.)]\s|>)|\*\*|__|`|^\s*\|.*\|\s*$|\[[^\]]+\]\([^)]+\)",
                    re.MULTILINE)
PREAMBLE = re.compile(r"^\s*(here is|here's|sure\b|certainly\b|below is|translation\s*:|english translation|"
                      r"english version|translated text)", re.IGNORECASE)
NOTE_LINE = re.compile(r"^\s*(note|notes|translator'?s note|n\.b\.)\s*:", re.IGNORECASE | re.MULTILINE)
REFUSAL = re.compile(r"\b(i can(?:'|no)t|i'm sorry|i am sorry|i'm unable|could you (?:please )?(?:provide|clarify))",
                     re.IGNORECASE)


def score(expected, parsed):
    parsed = parsed if isinstance(parsed, dict) else {"text": str(parsed or ""), "src_words": 0}
    text = (parsed.get("text") or "").strip()
    ref = (parsed.get("src_words") or 0) * expected["length_ratio"]
    out_words = word_count(text)
    ratio = out_words / ref if ref else 0.0
    nonanswer = (not text or bool(parsed.get("refusal"))
                 or (bool(REFUSAL.search(text[:300])) and ratio < 0.5)
                 or (text.rstrip().endswith("?") and ratio < 0.5))
    cats, notes = [], []
    if nonanswer:
        return {"passed": False, "valid": False, "nonanswer": True, "secondary": {"term_recall": 0.0,
                "forbidden_hits": 0, "length_ratio": ratio}, "categories": ["nonanswer"],
                "diff": f"nonanswer: {text[:120]!r}"}
    md = MD_OUT.search(text)
    pre = PREAMBLE.search(text.splitlines()[0] if text else "") or NOTE_LINE.search(text)
    if md:
        cats.append("markdown")
        notes.append(f"markdown {md.group(0).strip()[:20]!r}")
    if pre:
        cats.append("preamble")
        notes.append(f"framing {pre.group(0).strip()[:30]!r}")
    ok_terms, forb_hits = 0, 0
    for t in expected["terms"]:
        c = en_count(t["en"], text)
        if c >= t["min_count"]:
            ok_terms += 1
        elif c == 0:
            cats.append("missing_term")
            notes.append(f"missing {t['en']!r} ({t['sv']})")
        else:
            cats.append("repeat_not_kept")
            notes.append(f"{t['en']!r} {c}x < {t['min_count']} ({t['sv']})")
        for f in t["forbidden"]:
            if en_count(f, text):
                forb_hits += 1
                cats.append("forbidden_term")
                notes.append(f"forbidden {f!r} ({t['sv']})")
    lo, hi = expected["length_bounds"]
    if ratio < lo:
        cats.append("too_short")
        notes.append(f"length {ratio:.2f}x ref")
    elif ratio > hi:
        cats.append("too_long")
        notes.append(f"length {ratio:.2f}x ref")
    cats = list(dict.fromkeys(cats))
    passed = not cats
    return {"passed": passed, "valid": not (md or pre), "nonanswer": False,
            "secondary": {"term_recall": ok_terms / max(1, len(expected["terms"])), "forbidden_hits": forb_hits,
                          "length_ratio": round(ratio, 4)},
            "categories": cats, "diff": "; ".join(notes)}


def aggregate(rows):
    sec = [r.get("secondary") or {} for r in rows]
    n = max(1, len(sec))
    return {"term_recall_mean": sum(s.get("term_recall", 0.0) for s in sec) / n,
            "items_with_forbidden": sum(1 for s in sec if s.get("forbidden_hits")) / n,
            "length_ratio_mean": sum(s.get("length_ratio", 0.0) for s in sec) / n}


def failure_taxonomy():
    return ["missing_term", "repeat_not_kept", "forbidden_term", "markdown", "preamble", "too_long", "too_short",
            "nonanswer", "other"]


def answer_strings(expected):
    # The main glossary is part of the prompt by design. Only the unseen extension renderings must never be
    # put into a prompt.
    ext = {t["en"] for t in EXTENSION}
    return [t["en"] for t in expected["terms"] if t["en"] in ext and len(t["en"]) >= 5]


def legacy_markers():
    return [r"\bNEVER\b", r"\bALWAYS\b", r"IMPORTANT", r"(?i)plain text only", r"^GLOSSARY",
            r"^- laddare -> charger"]
