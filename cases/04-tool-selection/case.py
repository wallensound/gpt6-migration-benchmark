"""Case 04: tool selection and arguments. See spec.md (single source of truth)."""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from functools import lru_cache

from harness import entities

CASE_ID = "04"
NAME = "Tool selection and arguments"

REF = dt.date(2026, 11, 17)  # Tuesday

# --------------------------------------------------------------------------- tools

TOOLS = [
    {"name": "create_event",
     "description": "Create a calendar event at a specific date and start time (meetings, appointments, "
                    "scheduled calls, blocked time).",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string", "description": "Event title"},
         "date": {"type": "string", "description": "Date, YYYY-MM-DD"},
         "start_time": {"type": "string", "description": "Start time, 24-hour HH:MM"},
         "duration_minutes": {"type": "integer", "description": "Length in minutes"},
         "location": {"type": "string", "description": "City or place"},
         "attendees": {"type": "array", "items": {"type": "string"},
                       "description": "Full names of the other people attending"}},
         "required": ["title", "date", "start_time"]}},
    {"name": "find_contact",
     "description": "Look up a person's contact details (phone, email, job title) in the CRM.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Full name of the person"},
         "company": {"type": "string", "description": "Company the person works for"}},
         "required": ["name"]}},
    {"name": "send_email",
     "description": "Send an email from the user's mailbox.",
     "parameters": {"type": "object", "properties": {
         "to": {"type": "string", "description": "Recipient email address"},
         "subject": {"type": "string", "description": "Subject line"},
         "body": {"type": "string", "description": "Message body"},
         "cc": {"type": "string", "description": "Email address to copy in"}},
         "required": ["to", "subject"]}},
    {"name": "create_task",
     "description": "Add a to-do item with a due date to the user's task list. Tasks have no start time.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string", "description": "Task title"},
         "due_date": {"type": "string", "description": "Due date, YYYY-MM-DD"},
         "priority": {"type": "string", "enum": ["low", "normal", "high"], "description": "Default normal"},
         "assignee": {"type": "string", "description": "Full name of the person responsible, if not the user"}},
         "required": ["title", "due_date"]}},
    {"name": "log_call",
     "description": "Record a phone call that has already taken place in the CRM.",
     "parameters": {"type": "object", "properties": {
         "contact_name": {"type": "string", "description": "Full name of the person called"},
         "call_date": {"type": "string", "description": "Date of the call, YYYY-MM-DD"},
         "outcome": {"type": "string", "enum": ["connected", "voicemail", "no_answer"]},
         "duration_minutes": {"type": "integer", "description": "Length of the call in minutes"},
         "notes": {"type": "string", "description": "Short notes"}},
         "required": ["contact_name", "call_date", "outcome"]}},
    {"name": "search_docs",
     "description": "Full-text search over the company's internal documents (policies, contracts, decks, wiki).",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Search phrase"},
         "max_results": {"type": "integer", "description": "Number of results, default 10"}},
         "required": ["query"]}},
    {"name": "get_weather",
     "description": "Get the weather for a city, either current conditions or the forecast for a date.",
     "parameters": {"type": "object", "properties": {
         "location": {"type": "string", "description": "City name"},
         "date": {"type": "string", "description": "Forecast date, YYYY-MM-DD; omit for current conditions"},
         "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Default celsius"}},
         "required": ["location"]}},
    {"name": "convert_currency",
     "description": "Convert an amount from one currency to another at the current or a historical exchange rate.",
     "parameters": {"type": "object", "properties": {
         "amount": {"type": "number", "description": "Amount to convert"},
         "from_currency": {"type": "string", "description": "ISO 4217 code, e.g. EUR"},
         "to_currency": {"type": "string", "description": "ISO 4217 code, e.g. USD"},
         "date": {"type": "string", "description": "Date of the historical rate, YYYY-MM-DD; omit for today"}},
         "required": ["amount", "from_currency", "to_currency"]}},
]

RENAMED = {"create_task": "add_todo", "search_docs": "query_knowledge_base"}
SHIFT_DESCRIPTIONS = {
    "add_todo": "Put an item on the user's personal to-do list, due on a given day. To-do items never have a clock time.",
    "query_knowledge_base": "Look things up in the internal knowledge base: policy documents, contracts, slide decks "
                            "and wiki pages.",
}

TYPES = {
    "create_event": {"title": "text", "date": "date", "start_time": "time", "duration_minutes": "int",
                     "location": "city", "attendees": "names"},
    "create_task": {"title": "text", "due_date": "date", "priority": "enum", "assignee": "name"},
    "find_contact": {"name": "name", "company": "company"},
    "send_email": {"to": "email", "subject": "text", "cc": "email", "body": "free"},
    "log_call": {"contact_name": "name", "call_date": "date", "outcome": "enum", "duration_minutes": "int",
                 "notes": "free"},
    "search_docs": {"query": "text", "max_results": "int"},
    "get_weather": {"location": "city", "date": "date", "units": "enum"},
    "convert_currency": {"amount": "number", "from_currency": "code", "to_currency": "code", "date": "date"},
}
REQUIRED = {t["name"]: t["parameters"]["required"] for t in TOOLS}
DEFAULTS = {"create_task": {"priority": "normal"}, "search_docs": {"max_results": 10},
            "get_weather": {"units": "celsius"}}
TOOL_NAMES = [t["name"] for t in TOOLS]


def tool_defs(variant: str = "main") -> list[dict]:
    if variant != "shift":
        return json.loads(json.dumps(TOOLS))
    out = []
    for t in json.loads(json.dumps(TOOLS)):
        if t["name"] in RENAMED:
            t["name"] = RENAMED[t["name"]]
            t["description"] = SHIFT_DESCRIPTIONS[t["name"]]
        out.append(t)
    return out


# --------------------------------------------------------------------------- value pools

CITIES = ["Stockholm", "Malmö", "Uppsala", "Oslo", "Bergen", "Berlin", "Hamburg", "Amsterdam", "Madrid", "Paris",
          "London", "Dublin", "Edinburgh", "Manchester", "Barcelona", "Toronto", "Chicago", "Boston", "Tokyo",
          "Tallinn", "Riga", "Aarhus", "Oxford", "Seattle"]

EVENT_TITLES = {
    "en": ["Budget review", "Quarterly planning", "Design sync", "Contract walkthrough", "Onboarding session",
           "Vendor demo", "Hiring panel", "Roadmap check-in", "Board prep", "Sales kickoff", "Pricing workshop",
           "Customer feedback session", "Team retro", "Launch rehearsal", "Partner intro", "Dentist appointment",
           "Security briefing", "Strategy offsite planning", "Product demo", "Marketing sync"],
    "sv": ["Budgetgenomgång", "Kvartalsplanering", "Designavstämning", "Avtalsgenomgång", "Introduktionsmöte",
           "Leverantörsdemo", "Rekryteringsintervju", "Styrelseförberedelse", "Säljkickoff", "Prisworkshop",
           "Kundträff", "Teamretro", "Generalrepetition inför lanseringen", "Tandläkarbesök", "Säkerhetsgenomgång",
           "Produktdemo", "Marknadsavstämning", "Partnermöte"],
}
CALL_TITLES = {"en": ["Pricing call", "Intro call", "Follow-up call", "Renewal call", "Check-in call"],
               "sv": ["Prissamtal", "Introsamtal", "Uppföljningssamtal", "Förnyelsesamtal", "Avstämningssamtal"]}
TASK_TITLES = {
    "en": ["Renew the software licences", "Send the signed NDA", "Update the price list", "Review the draft contract",
           "Book the venue for the offsite", "Prepare the board slides", "File the expense report",
           "Order new laptops", "Draft the press release", "Check the insurance renewal", "Clean up the CRM pipeline",
           "Write the onboarding guide", "Approve the vacation requests", "Finalise the hiring plan",
           "Archive old project files", "Collect feedback on the proposal"],
    "sv": ["Förnya mjukvarulicenserna", "Skicka det signerade sekretessavtalet", "Uppdatera prislistan",
           "Granska avtalsutkastet", "Boka lokal till konferensen", "Förbereda styrelsebilderna",
           "Lämna in reseräkningen", "Beställa nya datorer", "Skriva pressmeddelandet", "Kolla försäkringsförnyelsen",
           "Städa upp säljpipelinen", "Skriva introduktionsguiden", "Godkänna semesteransökningarna",
           "Färdigställa rekryteringsplanen"],
}
SUBJECTS = {
    "en": ["Updated proposal", "Invoice question", "Meeting notes", "Next steps", "Contract renewal",
           "Quick question about the pilot", "Revised timeline", "Welcome aboard", "Project kickoff",
           "Delivery schedule", "Draft agreement", "Thanks for today", "Workshop follow-up", "Price update"],
    "sv": ["Uppdaterat förslag", "Fråga om fakturan", "Mötesanteckningar", "Nästa steg", "Förnyelse av avtalet",
           "Snabb fråga om piloten", "Reviderad tidplan", "Välkommen ombord", "Projektstart", "Leveransplan",
           "Avtalsutkast", "Tack för i dag", "Uppföljning efter workshopen", "Prisuppdatering"],
}
QUERIES = {
    "en": ["travel expense policy", "parental leave policy", "data retention policy", "onboarding checklist",
           "security incident runbook", "brand guidelines", "vendor contract template", "remote work policy",
           "office lease agreement", "customer churn analysis", "pricing strategy deck", "code of conduct",
           "procurement guidelines", "sales commission plan"],
    "sv": ["resepolicy", "föräldraledighetspolicy", "policy för datalagring", "introduktionschecklista",
           "varumärkesriktlinjer", "mall för leverantörsavtal", "distansarbetspolicy", "hyresavtal för kontoret",
           "analys av kundbortfall", "uppförandekod", "inköpsriktlinjer", "provisionsmodell för säljare"],
}

CURRENCIES = ["EUR", "USD", "GBP", "SEK", "NOK", "DKK", "CHF", "JPY"]
CUR_NAMES = {
    "en": {"EUR": ["euros"], "USD": ["US dollars"], "GBP": ["British pounds", "pounds"], "SEK": ["Swedish kronor"],
           "NOK": ["Norwegian kroner"], "DKK": ["Danish kroner"], "CHF": ["Swiss francs"], "JPY": ["Japanese yen"]},
    "sv": {"EUR": ["euro"], "USD": ["amerikanska dollar", "dollar"], "GBP": ["brittiska pund", "pund"],
           "SEK": ["kronor", "svenska kronor"], "NOK": ["norska kronor"], "DKK": ["danska kronor"],
           "CHF": ["schweizerfranc"], "JPY": ["japanska yen"]},
}
CUR_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
WEBMAIL = ["gmail.com", "outlook.com", "hotmail.com", "icloud.com"]

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
             "november", "december"]
WD_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_SV = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
NUM_EN = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
NUM_SV = {2: "två", 3: "tre", 4: "fyra", 5: "fem", 6: "sex", 7: "sju", 8: "åtta", 9: "nio", 10: "tio"}

DURATIONS = {
    "en": {15: ["15 minutes"], 30: ["30 minutes", "half an hour"], 45: ["45 minutes"],
           60: ["an hour", "60 minutes"], 90: ["90 minutes", "an hour and a half"], 120: ["two hours"]},
    "sv": {15: ["15 minuter"], 30: ["30 minuter", "en halvtimme"], 45: ["45 minuter"], 60: ["en timme"],
           90: ["90 minuter", "en och en halv timme"], 120: ["två timmar"]},
}
PRIORITY = {"en": {"high": ["high priority", "urgent"], "low": ["low priority"]},
            "sv": {"high": ["hög prioritet", "brådskande"], "low": ["låg prioritet"]}}
OUTCOME = {"en": {"connected": ["spoke with", "talked to"], "voicemail": ["left a voicemail"],
                  "no_answer": ["didn't pick up", "no answer"]},
           "sv": {"connected": ["pratade med", "fick tag på"], "voicemail": ["röstbrevlådan"],
                  "no_answer": ["svarade inte", "inget svar"]}}

NO_TOOL_TOPICS = {
    "unsupported_action": ["book a flight to a conference", "order a taxi to the airport", "set an alarm",
                           "reserve a table for a team lunch", "order new office chairs",
                           "transfer money to a supplier", "cancel a magazine subscription",
                           "print a report on the office printer", "book a hotel room for a trip",
                           "turn on the out-of-office auto-reply", "pay an overdue invoice",
                           "delete old files from the shared drive"],
    "general_question": ["explain what a letter of intent is", "explain the difference between gross and net margin",
                         "explain what EBITDA means", "explain what a SWOT analysis is",
                         "explain how compound interest works", "give tips for negotiating a supplier contract",
                         "explain the difference between a purchase order and an invoice",
                         "suggest how to structure a quarterly business review"],
    "writing_help": ["rewrite a blunt sentence (include the sentence) so it sounds more polite",
                     "suggest a catchy title for an internal newsletter",
                     "draft a short LinkedIn post about a product launch (the user only wants the text)",
                     "come up with a code name for an internal project",
                     "proofread a short sentence the user pastes in (include the sentence)"],
    "near_miss": ["ask in general how exchange rates are set", "ask why weather forecasts get less accurate further ahead",
                  "ask for tips on keeping a to-do list manageable", "ask how to write a good meeting invitation",
                  "ask what makes a good opening line for a sales call", "ask how to organise shared documents sensibly",
                  "ask how to keep a CRM tidy", "ask what a good email subject line looks like in general",
                  "ask how long a stand-up meeting should ideally be", "ask whether it is rude to send emails late at night"],
    "smalltalk": ["thank the assistant and say that's all for now", "ask the assistant what it can help with",
                  "say good job on the last answer and ask how it is doing"],
}

STYLE_FORM = ["a direct instruction", "a polite request (e.g. starting with 'Could you' or 'Can you')",
              "a short note that gives one sentence of context first and then the request",
              "a terse chat-style message with no greeting", "a message that opens with a brief 'Hi' or 'Hey'",
              "a request phrased as 'I need ...' or 'I'd like ...'"]
STYLE_LEN = ["one sentence", "one or two sentences", "two or three sentences"]
STYLE_REG = ["casual", "neutral", "formal", "hurried"]

LEGAL_SUFFIXES = sorted({s for c in entities.COUNTRIES for s in c[2]}, key=len, reverse=True)


# --------------------------------------------------------------------------- helpers

def ascii_fold(s: str) -> str:
    return entities.ascii_fold(s)


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _email(person: dict, domain: str) -> str:
    return f"{ascii_fold(person['first']).lower()}.{ascii_fold(person['last']).lower()}@{domain}"


def rel_future(rng, lang: str, max_days: int = 14) -> tuple[str, str]:
    opts = []  # (surface, offset)
    if lang == "en":
        opts += [("tomorrow", 1), ("the day after tomorrow", 2)]
        opts += [(f"in {NUM_EN[n]} days", n) for n in range(2, 11)]
        opts += [("in a week", 7), ("in two weeks", 14)]
        for i, wd in enumerate(WD_EN[:5]):  # Mon..Fri
            off = (i - 1) % 7 or 7
            if wd != "Tuesday":
                opts.append((rng.choice(["on ", "this "]) + wd if wd != "Monday" else "on Monday", off))
            opts.append((f"next {wd}", 6 + i))
    else:
        opts += [("i morgon", 1), ("i övermorgon", 2)]
        opts += [(f"om {NUM_SV[n]} dagar", n) for n in range(2, 11)]
        opts += [("om en vecka", 7), ("om två veckor", 14)]
        for i, wd in enumerate(WD_SV[:5]):
            off = (i - 1) % 7 or 7
            if wd != "tisdag":
                opts.append((f"på {wd}", off))
            opts.append((f"nästa {wd}", 6 + i))
    opts = [o for o in opts if o[1] <= max_days]
    s, off = rng.choice(opts)
    return s, _iso(REF + dt.timedelta(days=off))


def rel_past(rng, lang: str) -> tuple[str, str]:
    if lang == "en":
        opts = [("yesterday", 1), ("a week ago", 7)] + [(f"{NUM_EN[n]} days ago", n) for n in range(2, 11)]
        opts += [("last Wednesday", 6), ("last Thursday", 5), ("last Friday", 4)]
    else:
        opts = [("i går", 1), ("för en vecka sedan", 7)] + [(f"för {NUM_SV[n]} dagar sedan", n) for n in range(2, 11)]
        opts += [("i onsdags", 6), ("i torsdags", 5), ("i fredags", 4)]
    s, off = rng.choice(opts)
    return s, _iso(REF - dt.timedelta(days=off))


def abs_date(rng, lang: str, past: bool = False, max_days: int = 70) -> tuple[str, str]:
    if past:
        d = REF - dt.timedelta(days=rng.randint(2, 33))
    else:
        d = REF + dt.timedelta(days=rng.randint(2, max_days))
    y = d.year
    if lang == "en":
        m = MONTHS_EN[d.month - 1]
        forms = [f"{d.day} {m}", f"{m} {d.day}", f"{d.day} {m} {y}", f"{m} {d.day}, {y}", d.isoformat()]
    else:
        m = MONTHS_SV[d.month - 1]
        forms = [f"den {d.day} {m}", f"{d.day} {m}", f"{d.day} {m} {y}", d.isoformat()]
    return rng.choice(forms), _iso(d)


def pick_date(rng, lang, mode, past=False, max_days=70):
    """mode: absolute | relative | mixed."""
    if mode == "mixed":
        mode = "relative" if rng.random() < 0.4 else "absolute"
    if mode == "relative":
        return rel_past(rng, lang) if past else rel_future(rng, lang, max_days=min(14, max_days))
    return abs_date(rng, lang, past=past, max_days=max_days)


def time_surface(rng, lang, h, m) -> str:
    if lang == "en":
        h12 = h % 12 or 12
        ap = "am" if h < 12 else "pm"
        forms = [f"{h:02d}:{m:02d}", f"{h12}:{m:02d} {ap}"]
        if m == 0:
            forms += [f"{h12}pm" if h >= 12 else f"{h12}am", f"{h12} {ap}"]
    else:
        forms = [f"kl. {h}.{m:02d}", f"{h:02d}:{m:02d}"]
        if m == 0:
            forms.append(f"klockan {h}")
    return rng.choice(forms)


def pick_time(rng, lang):
    h = rng.randint(8, 17)
    m = rng.choice([0, 0, 15, 30, 45])
    return time_surface(rng, lang, h, m), f"{h:02d}:{m:02d}"


def amount_value(rng, cur):
    if cur == "JPY":
        return float(rng.choice([5000, 12000, 25000, 80000, 150000]))
    k = rng.random()
    if k < 0.45:
        return float(rng.randint(2, 99) * 10)
    if k < 0.8:
        return float(rng.randint(1, 40) * 250)
    return round(rng.randint(1000, 99999) / 100, 2)


def amount_surface(rng, lang, amount, cur):
    whole = amount == int(amount)
    if lang == "en":
        num = (f"{int(amount):,}" if rng.random() < 0.6 else str(int(amount))) if whole else (
            f"{amount:,.2f}" if rng.random() < 0.6 else f"{amount:.2f}")
        forms = [f"{num} {rng.choice(CUR_NAMES['en'][cur])}", f"{num} {cur}", f"{cur} {num}"]
        if cur in CUR_SYMBOL:
            forms += [f"{CUR_SYMBOL[cur]}{num}"] * 2
    else:
        if whole:
            n = int(amount)
            num = f"{n:,}".replace(",", " ") if (n >= 1000 and rng.random() < 0.6) else str(n)
        else:
            ip = int(amount)
            ipart = f"{ip:,}".replace(",", " ") if ip >= 1000 else str(ip)
            num = f"{ipart},{round((amount - ip) * 100):02d}"
        forms = [f"{num} {rng.choice(CUR_NAMES['sv'][cur])}", f"{num} {cur}"]
    return rng.choice(forms)


def to_cur_surface(rng, lang, cur):
    return rng.choice(CUR_NAMES[lang][cur] + [cur])


@lru_cache(maxsize=None)
def _people():
    return entities.people()


def _company(rng, variant):
    return rng.choice(entities.companies("shift" if variant == "shift" else "main"))


def _persons(rng, k):
    return rng.sample(_people(), k)


# --------------------------------------------------------------------------- planning

def slices():
    return ["plain", "relative_dates", "optional_omitted", "lookalike_tools", "multi_candidate", "no_tool"]


def slice_weights(variant):
    return {"plain": 17, "relative_dates": 17, "optional_omitted": 17, "lookalike_tools": 17,
            "multi_candidate": 17, "no_tool": 15}


def _new_plan(rng, variant, tool, slice_):
    lang = "sv" if variant == "shift" else "en"
    return {"variant": variant, "lang": lang, "tool": tool, "args": {}, "must": [], "quoted": [], "intent": [],
            "rules": [], "people": [], "companies": [], "cities": [], "corrections": [], "kind": slice_,
            "style": {"form": rng.choice(STYLE_FORM), "length": rng.choice(STYLE_LEN),
                      "register": rng.choice(STYLE_REG)}, "notes": []}


def _add(p, arg, value, surface, intent, quoted=False):
    if arg is not None:
        p["args"][arg] = value
    if surface is not None:
        p["must"].append(surface)
        if quoted:
            p["quoted"].append(surface)
    if intent:
        p["intent"].append(intent)


def _want(rng, opt_mode):
    if opt_mode == "none":
        return False
    if opt_mode == "all":
        return True
    return rng.random() < 0.5


def _fill(rng, p, tool, opt_mode="random", date_mode="absolute", correct=None, title_pool=None):
    """Sample values for `tool` into plan p. correct = argument whose value the user corrects (M1)."""
    L = p["lang"]
    variant = p["variant"]

    def corr(arg, sampler, fmt):
        """Sample a value; if this arg is corrected, sample an old value too and register the correction."""
        s, v = sampler()
        if correct == arg:
            for _ in range(20):
                s0, v0 = sampler()
                if v0 != v and s0.lower() not in s.lower() and s.lower() not in s0.lower():
                    break
            p["corrections"].append([s0, s])
            p["must"].append(s0)
            p["notes"].append(f"the user first says {s0!r} for the {arg}, then corrects it to {s!r}; "
                              f"the final value {v!r} is correct (rule M1)")
        return s, v

    if tool == "create_event":
        title = rng.choice(title_pool or EVENT_TITLES[L])
        _add(p, "title", title, title, f'a calendar event titled "{title}"', quoted=True)
        s, v = corr("date", lambda: pick_date(rng, L, date_mode), None)
        _add(p, "date", v, s, f"on the day: {s}")
        s, v = corr("start_time", lambda: pick_time(rng, L), None)
        _add(p, "start_time", v, s, f"starting at {s}")
        if _want(rng, opt_mode):
            d = rng.choice(list(DURATIONS[L]))
            s = rng.choice(DURATIONS[L][d])
            _add(p, "duration_minutes", d, s, f"lasting {s}")
        if _want(rng, opt_mode):
            c = rng.choice(CITIES)
            p["cities"].append(c)
            _add(p, "location", c, c, f"taking place in {c}")
        if _want(rng, opt_mode):
            ps = _persons(rng, rng.choice([1, 1, 2]))
            names = [x["name"] for x in ps]
            p["people"] += names
            for n in names:
                p["must"].append(n)
            p["args"]["attendees"] = names
            p["intent"].append("with " + " and ".join(names) + " attending")
    elif tool == "create_task":
        title = rng.choice(TASK_TITLES[L])
        _add(p, "title", title, title, f'a to-do titled "{title}"', quoted=True)
        s, v = corr("due_date", lambda: pick_date(rng, L, date_mode), None)
        _add(p, "due_date", v, s, f"due {s}")
        if _want(rng, opt_mode):
            pr = rng.choice(["high", "high", "low"])
            s = rng.choice(PRIORITY[L][pr])
            _add(p, "priority", pr, s, f"marked as {s}")
        if _want(rng, opt_mode):
            a = _persons(rng, 1)[0]["name"]
            p["people"].append(a)
            _add(p, "assignee", a, a, f"assigned to {a}")
    elif tool == "find_contact":
        def samp():
            n = _persons(rng, 1)[0]["name"]
            return n, n
        s, v = corr("name", samp, None)
        p["people"].append(v)
        if p["corrections"]:
            p["people"].append(p["corrections"][-1][0])
        _add(p, "name", v, s, f"look up the contact details (phone number, email) of {s}")
        if _want(rng, opt_mode):
            c = _company(rng, variant)
            p["companies"].append(c["name"])
            _add(p, "company", c["name"], c["name"], f"who works at {c['name']}")
    elif tool == "send_email":
        person = _persons(rng, 1)[0]
        comp = _company(rng, variant)
        p["people"].append(person["name"])
        addr = _email(person, comp["domain"])
        if correct == "to":
            other = _persons(rng, 1)[0]
            old = _email(other, _company(rng, variant)["domain"])
            p["corrections"].append([old, addr])
            p["must"].append(old)
            p["notes"].append(f"the user first gives {old}, then corrects it to {addr}; {addr} is correct (rule M1)")
        if correct == "webmail":
            loc = ascii_fold(person["first"]).lower() + "." + ascii_fold(person["last"]).lower()
            private = f"{loc}{rng.choice(['', str(rng.randint(70, 99))])}@{rng.choice(WEBMAIL)}"
            p["must"].append(private)
            p["webmail"] = private
            p["notes"].append(f"two addresses are given for the recipient: work {addr} and personal {private}; "
                              f"the work address {addr} is correct (rule M2), whatever the order")
            p["intent"].append(f"the recipient has two addresses, {addr} (work) and {private} (private); mention "
                               f"both in {rng.choice(['that order', 'the opposite order'])}, without saying which one "
                               f"to use")
        _add(p, "to", addr, addr, "send an email to this person" if correct == "webmail" else
             f"send an email to {addr}")
        subj = rng.choice(SUBJECTS[L])
        _add(p, "subject", subj, subj, f'with the subject "{subj}"', quoted=True)
        if _want(rng, opt_mode):
            cc_p = _persons(rng, 1)[0]
            cc = _email(cc_p, comp["domain"])
            _add(p, "cc", cc, cc, f"copying in {cc}")
        p["intent"].append("and say in a few words what the email should say (no names, dates, numbers or amounts)")
    elif tool == "log_call":
        def samp():
            n = _persons(rng, 1)[0]["name"]
            return n, n
        s, v = samp()
        p["people"].append(v)
        s, d = corr("call_date", lambda: pick_date(rng, L, date_mode, past=True), None)
        oc = rng.choice(["connected", "connected", "voicemail", "no_answer"])
        osurf = rng.choice(OUTCOME[L][oc])
        _add(p, "contact_name", v, v, f"record in the CRM a phone call with {v} that already happened")
        _add(p, "call_date", d, s, f"the call was {s}")
        _add(p, "outcome", oc, osurf, f"outcome expressed with the words: {osurf}")
        if _want(rng, opt_mode):
            mins = rng.randint(4, 40)
            ms = f"{mins} {'minutes' if L == 'en' else 'minuter'}"
            _add(p, "duration_minutes", mins, ms, f"the call lasted {ms}")
    elif tool == "search_docs":
        q = rng.choice(QUERIES[L])
        _add(p, "query", q, q, f'search the internal documents for "{q}"', quoted=True)
        if _want(rng, opt_mode):
            n = rng.choice([3, 5, 20, 25])
            s = rng.choice([f"top {n}", f"{n} results"]) if L == "en" else rng.choice([f"{n} träffar", f"topp {n}"])
            _add(p, "max_results", n, s, f"wants the {s}")
    elif tool == "get_weather":
        def samp():
            c = rng.choice(CITIES)
            return c, c
        s, c = corr("location", samp, None)
        p["cities"].append(c)
        if p["corrections"] and correct == "location":
            p["cities"].append(p["corrections"][-1][0])
        _add(p, "location", c, c, f"the weather in {s}")
        if correct == "date" or _want(rng, opt_mode) or date_mode == "relative":
            s, v = corr("date", lambda: pick_date(rng, L, date_mode, max_days=10), None)
            _add(p, "date", v, s, f"for the day: {s}")
        else:
            p["intent"].append("right now (current conditions; do not mention any day)")
        if _want(rng, opt_mode):
            _add(p, "units", "fahrenheit", "Fahrenheit", "in Fahrenheit")
    elif tool == "convert_currency":
        fc, tc = rng.sample(CURRENCIES, 2)
        if correct == "to_currency":
            tc0 = rng.choice([c for c in CURRENCIES if c not in (fc, tc)])
        amt = amount_value(rng, fc)
        s = amount_surface(rng, L, amt, fc)
        if correct == "amount":
            for _ in range(20):
                a0 = amount_value(rng, fc)
                s0 = amount_surface(rng, L, a0, fc)
                if a0 != amt and s0.lower() not in s.lower() and s.lower() not in s0.lower():
                    break
            p["corrections"].append([s0, s])
            p["must"].append(s0)
            p["notes"].append(f"the user first says {s0!r}, then corrects it to {s!r}; {amt} is correct (rule M1)")
        p["args"]["amount"] = amt
        p["args"]["from_currency"] = fc
        p["must"].append(s)
        p["intent"].append(f"convert {s}")
        def _clash(a, b):
            return a.lower() in b.lower() or b.lower() in a.lower()

        for _ in range(30):
            ts = to_cur_surface(rng, L, tc)
            if not any(_clash(ts, x) for x in p["must"]):
                break
        else:
            ts = tc
        if correct == "to_currency":
            for _ in range(30):
                ts0 = to_cur_surface(rng, L, tc0)
                if not any(_clash(ts0, x) for x in p["must"] + [ts]):
                    break
            else:
                ts0 = tc0
            p["corrections"].append([ts0, ts])
            p["must"].append(ts0)
            p["notes"].append(f"the user first asks for {ts0!r}, then changes it to {ts!r}; {tc} is correct (rule M1)")
        _add(p, "to_currency", tc, ts, f"into {ts}")
        if date_mode == "relative" or _want(rng, opt_mode):
            s, v = pick_date(rng, L, date_mode, past=True)
            _add(p, "date", v, s, f"using the historical exchange rate from {s}")
        else:
            p["intent"].append("(do not mention any day or which exchange rate to use)")
    for old, new in p["corrections"]:
        p["intent"].append(f"first say {old!r}, then correct yourself in the same message and replace it with "
                           f"{new!r} (e.g. 'no wait', 'actually, make that'); {new!r} must clearly be the final choice")
    return p


def plan(rng, slice, variant="main"):
    s = slice
    if s == "no_tool":
        p = _new_plan(rng, variant, None, s)
        kind = rng.choice(["unsupported_action", "unsupported_action", "general_question", "writing_help",
                           "near_miss", "near_miss", "smalltalk"])
        p["kind"] = kind
        p["topic"] = rng.choice(NO_TOOL_TOPICS[kind])
        return p
    if s == "plain":
        tool = rng.choice(TOOL_NAMES)
        return _fill(rng, _new_plan(rng, variant, tool, s), tool, "random", "absolute")
    if s == "relative_dates":
        tool = rng.choice(["create_event", "create_event", "create_task", "create_task", "log_call", "log_call",
                           "get_weather", "convert_currency"])
        return _fill(rng, _new_plan(rng, variant, tool, s), tool, "random", "relative")
    if s == "optional_omitted":
        tool = rng.choice(TOOL_NAMES)
        return _fill(rng, _new_plan(rng, variant, tool, s), tool, "none", "mixed")
    if s == "lookalike_tools":
        kind = rng.choice(["event_task_wording", "task_event_wording", "future_call", "past_call"])
        tool = {"event_task_wording": "create_event", "task_event_wording": "create_task",
                "future_call": "create_event", "past_call": "log_call"}[kind]
        p = _new_plan(rng, variant, tool, s)
        p["kind"] = kind
        if kind == "future_call":
            L = p["lang"]
            title = rng.choice(CALL_TITLES[L])
            person = _persons(rng, 1)[0]["name"]
            _add(p, "title", title, title, f'schedule a phone call titled "{title}" with {person} (a future call)',
                 quoted=True)
            ds, dv = pick_date(rng, L, "mixed")
            ts, tv = pick_time(rng, L)
            _add(p, "date", dv, ds, f"on the day: {ds}")
            _add(p, "start_time", tv, ts, f"at {ts}")
            p["args"]["attendees"] = [person]
            p["people"].append(person)
            p["must"].append(person)
            return p
        _fill(rng, p, tool, "random", "mixed", title_pool=TASK_TITLES[p["lang"]] if kind == "event_task_wording" else None)
        if kind == "event_task_wording":
            p["rules"].append("Phrase it as something the user has to do ('I need to', 'make sure I', 'I have "
                              "to'), not as a meeting, and do not use the words calendar, meeting or event; it "
                              "still happens at the given clock time.")
        elif kind == "task_event_wording":
            p["rules"].append("Use calendar-like wording such as 'schedule', 'plan', 'pencil in' or 'put ... down "
                              "for', but give no clock time and no time of day; it is a to-do for that day.")
        else:
            p["rules"].append("Make clear the call already happened and the user wants it noted down.")
        return p
    if s == "multi_candidate":
        choice = rng.choice([("create_event", "date"), ("create_event", "start_time"), ("create_task", "due_date"),
                             ("get_weather", "location"), ("get_weather", "date"), ("convert_currency", "amount"),
                             ("convert_currency", "to_currency"), ("send_email", "to"), ("send_email", "webmail"),
                             ("send_email", "webmail"), ("find_contact", "name"), ("log_call", "call_date")])
        tool, arg = choice
        p = _new_plan(rng, variant, tool, s)
        p["corrected_arg"] = arg
        return _fill(rng, p, tool, "random", "mixed", correct=arg)
    raise ValueError(s)


# --------------------------------------------------------------------------- generation

def _lang_line(p):
    return ("Write it in natural, everyday Swedish (the strings below stay exactly as given)."
            if p["lang"] == "sv" else "Write it in natural English.")


def _style(p):
    st = p["style"]
    return f"{st['form']}, {st['length']}, {st['register']} tone"


def generator_prompt(plan):
    p = plan
    if p["tool"] is None:
        return (
            "You are writing one test input for an AI work assistant. The assistant can schedule calendar events, "
            "add to-dos, look up contacts, send emails, log phone calls, search internal documents, check the weather "
            "and convert currency amounts.\n\n"
            f"Write a message in which the user wants to: {p['topic']}.\n"
            "The message must NOT ask for any of the assistant's actions listed above (no scheduling, to-do, contact "
            "lookup, sending an email, logging a call, searching documents, weather lookup or converting a specific "
            "amount). It is a request that none of those actions can handle.\n"
            f"{_lang_line(p)}\nStyle: {_style(p)}.\n"
            "Use no email addresses and no real or invented person names. Do not sign the message.\n"
            "Output only the message text, nothing else.")
    must = "\n".join(f"- {m}" for m in p["must"])
    lines = ["You are writing one test input for an AI work assistant that can call tools.", "",
             "Write the message a user types to the assistant. What the user wants: " + "; ".join(p["intent"]) + ".",
             _lang_line(p), "",
             "The message MUST contain each of these strings exactly as written (same spelling, digits, symbols and "
             "punctuation; only the capitalisation of a first letter may change):", must]
    if p["quoted"]:
        lines.append("Put each of these inside double quotation marks in the message: " + "; ".join(p["quoted"]) + ".")
    lines += ["", "Rules:",
              "- Mention no other dates, weekdays, times of day, durations, people, companies, cities, email addresses, "
              "amounts or currencies than the ones in the list. Use no digits outside the listed strings."]
    missing = _unplanned_info(p)
    if missing:
        lines.append(f"- Do not mention {missing}.")
    lines += [f"- {r}" for r in p["rules"]]
    lines += ["- Do not sign the message with a name. Do not use greetings that mention a time of day.",
              f"- Style: {_style(p)}. Vary the wording; do not just list the strings.",
              "- Output only the message text, nothing else: no labels, no explanations, no surrounding quotes."]
    return "\n".join(lines)


def _unplanned_info(p) -> str:
    t, a = p["tool"], p["args"]
    out = []
    if t == "create_event":
        if "duration_minutes" not in a:
            out.append("how long it lasts or an end time")
        if "location" not in a:
            out.append("where it takes place")
        if "attendees" not in a:
            out.append("any other person")
    elif t == "create_task":
        if "priority" not in a:
            out.append("priority or urgency")
        if "assignee" not in a:
            out.append("anyone else doing the task")
    elif t == "find_contact":
        if "company" not in a:
            out.append("which company the person works for")
    elif t == "send_email":
        if "cc" not in a:
            out.append("copying anyone in")
    elif t == "log_call":
        if "duration_minutes" not in a:
            out.append("how long the call lasted")
    elif t == "search_docs":
        if "max_results" not in a:
            out.append("how many results to show")
    elif t == "get_weather":
        if "units" not in a:
            out.append("temperature units")
    return ", ".join(out)


def make_input(plan, text):
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    return t


# --------------------------------------------------------------------------- verification

_DATE_WORDS = {
    "en": r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|june|july|"
          r"august|september|october|november|december|today|tonight|tomorrow|yesterday|weekend|week|weeks|month|"
          r"days|morning|afternoon|evening|noon|midnight|eod|asap)\b",
    "sv": r"\b(måndag\w*|tisdag\w*|onsdag\w*|torsdag\w*|fredag\w*|lördag\w*|söndag\w*|januari|februari|mars|april|"
          r"maj|juni|juli|augusti|september|oktober|november|december|idag|i dag|imorgon|i morgon|igår|i går|"
          r"övermorgon|morgon|vecka|veckan|veckor|månad|dagar|eftermiddag\w*|förmiddag\w*|kväll\w*|ikväll)\b",
}
_CUR_WORDS = r"(\b(eur|usd|gbp|sek|nok|dkk|chf|jpy|euros?|dollars?|pounds?|kronor|kroner|krona|francs?|franc|yen|kr)\b|[€$£¥])"


@lru_cache(maxsize=None)
def _name_regex():
    firsts = sorted(set(entities.FIRST), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(map(re.escape, firsts)) + r")\b")


@lru_cache(maxsize=None)
def _company_regex():
    names = sorted({c["name"] for c in entities.companies(None)}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")


def _city_regex():
    return re.compile(r"\b(" + "|".join(map(re.escape, CITIES)) + r")\b")


def _strip_planned(text, strings):
    out = text
    for s in sorted(set(strings), key=len, reverse=True):
        out = re.sub(re.escape(s), " ", out, flags=re.IGNORECASE)
    return out


def verify(plan, text):
    p = plan
    if not text or len(text) < 8:
        return False, "empty or too short"
    if len(text) > 900:
        return False, "too long"
    low = text.casefold()
    if p["tool"] is None:
        if "@" in text:
            return False, "email address in a no-tool item"
        if re.search(r"^(here is|here's|message:)", low):
            return False, "meta preamble"
        return True, ""
    for m in p["must"]:
        if m.casefold() not in low:
            return False, f"planned string missing: {m!r}"
    for old, new in p["corrections"]:
        if low.find(old.casefold()) > low.rfind(new.casefold()) or low.rfind(old.casefold()) > low.rfind(new.casefold()):
            return False, f"correction order wrong: {old!r} -> {new!r}"
    extra = p["people"] + [n.split()[0] for n in p["people"]] + p["cities"] + p["companies"]
    rest = _strip_planned(text, p["must"] + extra)
    if re.search(r"\d", rest):
        return False, "unplanned digits: " + ", ".join(re.findall(r"\S*\d\S*", rest))[:80]
    if "@" in rest:
        return False, "unplanned email address"
    m = re.search(_DATE_WORDS[p["lang"]], rest, flags=re.IGNORECASE)
    if m:
        return False, f"unplanned date/time word: {m.group(0)!r}"
    m = re.search(r"\b\d{1,2}\s?(am|pm)\b", rest, flags=re.IGNORECASE)
    if m:
        return False, "unplanned time"
    m = re.search(_CUR_WORDS, rest, flags=re.IGNORECASE)
    if m:
        return False, f"unplanned currency: {m.group(0)!r}"
    m = _name_regex().search(rest)
    if m:
        return False, f"unplanned person: {m.group(0)!r}"
    m = _company_regex().search(rest)
    if m:
        return False, f"unplanned company: {m.group(0)!r}"
    m = _city_regex().search(rest)
    if m:
        return False, f"unplanned city: {m.group(0)!r}"
    for q in p["quoted"]:
        if not re.search(r"[\"“”'‘’«»]\s*" + re.escape(q) + r"[.,!?]?\s*[\"“”'‘’«»]", text, flags=re.IGNORECASE):
            return False, f"quoted string not in quotes: {q!r}"
    return True, ""


_TOOL_SUMMARY = ("create_event (something at a clock time), create_task (to-do with a due date, no clock time), "
                 "find_contact, send_email, log_call (a call that already happened), search_docs, get_weather, "
                 "convert_currency")


def verifier_brief(plan):
    p = plan
    ref = ("Reference date: Tuesday 17 November 2026. 'next <weekday>' means that weekday in the week of 23-29 "
           "November; 'on/this <weekday>' (Swedish 'på <weekday>') means the first such day after today; 'last "
           "<weekday>' (Swedish 'i fredags' etc.) means that weekday in 9-15 November.")
    if p["tool"] is None:
        return ("The assistant has eight functions: " + _TOOL_SUMMARY + ". For this message NONE of them applies: "
                "the correct response is a plain-text reply with no function call. Anything that makes one of the "
                "functions clearly appropriate (a concrete request to schedule something, add a to-do, look up a "
                "contact, send an email, log a call, search internal documents, get the weather for a place, or "
                "convert a specific amount) would change the answer.")
    name = RENAMED.get(p["tool"]) if p["variant"] == "shift" and p["tool"] in RENAMED else p["tool"]
    brief = (f"The assistant has eight functions: {_TOOL_SUMMARY}. The correct response is exactly one call to "
             f"{name} with exactly these arguments: {json.dumps(p['args'], ensure_ascii=False)}. {ref} "
             "Rules: a request with a clock time is an event, without one a to-do; free-text email body or call "
             "notes do not matter. ")
    if p["notes"]:
        brief += "Note: " + "; ".join(p["notes"]) + ". "
    brief += ("The answer changes if the text gives a different or second value for any of these arguments "
              "(other than the planned correction), gives a value for another argument of this function that is "
              "not listed (e.g. a duration, place, extra people, priority, assignee, company, cc, number of "
              "results, units, a forecast or rate date), or makes a different function equally suitable.")
    return brief


# --------------------------------------------------------------------------- label

def label(plan):
    t = plan["tool"]
    if t is None:
        return {"tool": None, "args": {}, "types": {}, "defaults": {}}
    name = RENAMED[t] if plan.get("variant") == "shift" and t in RENAMED else t
    args = dict(plan["args"])
    return {"tool": name, "args": args, "types": TYPES[t], "defaults": DEFAULTS.get(t, {})}


def item_extras(plan):
    return {"tools": tool_defs("shift")} if plan.get("variant") == "shift" else {}


def tools(item, settings):
    return item.get("tools") or tool_defs("main")


def answer_strings(expected):
    out = []
    for k, v in (expected.get("args") or {}).items():
        typ = (expected.get("types") or {}).get(k)
        if typ in ("text", "name", "email", "company"):
            out.append(str(v))
        elif typ == "names":
            out += [str(x) for x in v]
    return [s for s in out if len(s) >= 5]


# --------------------------------------------------------------------------- normalisation

def _fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", ascii_fold(s)) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().casefold()


_MONTH_IDX = {m.lower(): i + 1 for i, m in enumerate(MONTHS_EN)}


def norm_date(v):
    if not isinstance(v, str):
        return None
    s = v.strip()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T ].*)?", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m1 = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
        m2 = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
        if m1 and m1.group(2).lower() in _MONTH_IDX:
            d, mo, y = int(m1.group(1)), _MONTH_IDX[m1.group(2).lower()], int(m1.group(3))
        elif m2 and m2.group(1).lower() in _MONTH_IDX:
            mo, d, y = _MONTH_IDX[m2.group(1).lower()], int(m2.group(2)), int(m2.group(3))
        else:
            return None
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def norm_time(v):
    if not isinstance(v, str):
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::00)?", v.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def norm_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v):
        return int(v)
    return None


def norm_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").replace(" ", "").replace(" ", ""))
        except ValueError:
            return None
    return None


def norm_text(v):
    if not isinstance(v, str):
        return None
    s = v.strip().replace("’", "'").replace("‘", "'")
    s = s.strip("\"“”'«» \t")
    s = re.sub(r"[.!?]+$", "", s).strip()
    return re.sub(r"\s+", " ", s).casefold()


def norm_name(v):
    return _fold(v) if isinstance(v, str) else None


def norm_company(v):
    if not isinstance(v, str):
        return None
    s = v.strip()
    for suf in LEGAL_SUFFIXES:
        if s.lower().endswith(" " + suf.lower()):
            s = s[: -len(suf) - 1]
            break
    return _fold(s)


def norm_value(typ, v):
    if typ == "date":
        return norm_date(v)
    if typ == "time":
        return norm_time(v)
    if typ == "int":
        return norm_int(v)
    if typ == "number":
        n = norm_number(v)
        return None if n is None else round(n, 3)
    if typ == "code":
        return v.strip().upper() if isinstance(v, str) else None
    if typ == "enum":
        return v.strip().casefold() if isinstance(v, str) else None
    if typ == "email":
        if not isinstance(v, str):
            return None
        s = v.strip().casefold()
        return s[7:] if s.startswith("mailto:") else s
    if typ == "name":
        return norm_name(v)
    if typ == "names":
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return None
        return sorted({_fold(x) for x in v})
    if typ == "city":
        return _fold(v.split(",")[0]) if isinstance(v, str) else None
    if typ == "company":
        return norm_company(v)
    if typ == "text":
        return norm_text(v)
    return v


def _empty(v):
    return v is None or (isinstance(v, (str, list, dict)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


# --------------------------------------------------------------------------- parse and score

def parse(output, settings, item):
    try:
        if isinstance(output, list):
            output = output[0] if output else {}
        output = output or {}
        calls = []
        for tc in output.get("tool_calls") or []:
            raw = tc.get("arguments")
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                args = None
            if not isinstance(args, dict):
                args = None
            calls.append({"name": tc.get("name"), "args": args, "raw": raw if isinstance(raw, str) else json.dumps(raw)})
        return {"calls": calls, "text": output.get("text") or "", "refusal": output.get("refusal"),
                "status": output.get("status")}
    except Exception as e:  # noqa: BLE001
        return {"calls": [], "text": "", "refusal": None, "status": f"parse_error: {e}"}


_REFUSAL = re.compile(r"\b(i can'?t|i cannot|i'm unable|i am unable|sorry|kan inte|tyvärr)\b", re.IGNORECASE)


def score(expected, parsed):
    parsed = parsed if isinstance(parsed, dict) else {"calls": [], "text": ""}
    calls = parsed.get("calls") or []
    text = (parsed.get("text") or "").strip()
    exp_tool = expected.get("tool")
    sec = {"tool_correct": 0.0}
    if exp_tool is None:
        sec["false_call"] = float(bool(calls))
        ok = not calls
        sec["tool_correct"] = float(ok)
        valid = (not calls and bool(text)) or all(c.get("args") is not None for c in calls)
        cats = [] if ok else ["false_call"] + (["multiple_calls"] if len(calls) > 1 else [])
        diff = "" if ok else "expected no call, got " + ", ".join(f"{c.get('name')}({c.get('raw')})" for c in calls)
        return {"passed": ok, "valid": bool(valid), "nonanswer": (not calls and not text),
                "secondary": sec, "categories": cats, "diff": diff[:400]}
    sec["missed_call"] = float(not calls)
    sec["arg_accuracy"] = 0.0
    if not calls:
        non = (not text) or text.rstrip().endswith("?") or bool(parsed.get("refusal")) or bool(_REFUSAL.search(text))
        return {"passed": False, "valid": True, "nonanswer": bool(non), "secondary": sec,
                "categories": ["nonanswer"] if non else ["missed_call"],
                "diff": f"expected {exp_tool}, got text: {text[:200]!r}"}
    if len(calls) > 1:
        sec["tool_correct"] = 0.0
        return {"passed": False, "valid": False, "nonanswer": False, "secondary": sec, "categories": ["multiple_calls"],
                "diff": f"expected one call to {exp_tool}, got {len(calls)}: " +
                        ", ".join(str(c.get("name")) for c in calls)}
    c = calls[0]
    known = set(TOOL_NAMES) | set(RENAMED.values())
    if c.get("name") != exp_tool:
        valid = c.get("name") in known and c.get("args") is not None
        cats = ["wrong_tool"] if valid else ["bad_arguments"]
        return {"passed": False, "valid": valid, "nonanswer": False, "secondary": sec, "categories": cats,
                "diff": f"expected {exp_tool}, got {c.get('name')}({str(c.get('raw'))[:200]})"}
    sec["tool_correct"] = 1.0
    args = c.get("args")
    if args is None:
        return {"passed": False, "valid": False, "nonanswer": False, "secondary": sec, "categories": ["bad_arguments"],
                "diff": f"arguments not a JSON object: {str(c.get('raw'))[:200]}"}
    types, exp_args, defaults = expected["types"], expected["args"], expected.get("defaults") or {}
    cats, diffs, right = [], [], 0
    for k, ev in exp_args.items():
        typ = types.get(k, "text")
        if k not in args or _empty(args.get(k)):
            cats.append("missing_arg")
            diffs.append(f"{k}: missing (expected {ev!r})")
            continue
        if norm_value(typ, args[k]) == norm_value(typ, ev) and norm_value(typ, ev) is not None:
            right += 1
        else:
            cats.append("date_resolution" if typ == "date" else "wrong_value")
            diffs.append(f"{k}: expected {ev!r}, got {args[k]!r}")
    for k, v in args.items():
        if k in exp_args or types.get(k) == "free" or _empty(v):
            continue
        if k in defaults and norm_value(types.get(k, "text"), v) == norm_value(types.get(k, "text"), defaults[k]):
            continue
        cats.append("extra_arg")
        diffs.append(f"{k}: unexpected {v!r}")
    sec["arg_accuracy"] = right / len(exp_args) if exp_args else 1.0
    sec["extra_args"] = float(sum(1 for x in cats if x == "extra_arg"))
    ok = not cats
    return {"passed": ok, "valid": True, "nonanswer": False, "secondary": sec,
            "categories": sorted(set(cats)), "diff": "; ".join(diffs)[:400]}


def aggregate(rows):
    tool_rows = [r for r in rows if "missed_call" in (r.get("secondary") or {})]
    no_rows = [r for r in rows if "false_call" in (r.get("secondary") or {})]
    right_tool = [r for r in tool_rows if r["secondary"].get("tool_correct")]
    n = len(rows)
    return {
        "tool_name_accuracy": sum(r["secondary"].get("tool_correct", 0) for r in rows if r.get("secondary")) / n if n else 0.0,
        "argument_accuracy": (sum(r["secondary"].get("arg_accuracy", 0) for r in right_tool) / len(right_tool)
                              if right_tool else 0.0),
        "false_call_rate": (sum(r["secondary"]["false_call"] for r in no_rows) / len(no_rows)) if no_rows else 0.0,
        "missed_call_rate": (sum(r["secondary"]["missed_call"] for r in tool_rows) / len(tool_rows)) if tool_rows else 0.0,
        "n_tool_items": len(tool_rows), "n_no_tool_items": len(no_rows),
    }


def failure_taxonomy():
    return ["wrong_tool", "missed_call", "false_call", "multiple_calls", "wrong_value", "date_resolution",
            "missing_arg", "extra_arg", "bad_arguments", "nonanswer", "other"]


def legacy_markers():
    return [r"Today is Tuesday, 17 November 2026", r"\bALWAYS\b", r"\bNEVER\b", r"^IMPORTANT", r"[Bb]e concise",
            r"\bDO NOT\b"]
