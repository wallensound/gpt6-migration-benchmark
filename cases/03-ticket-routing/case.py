"""Case 03: route one customer message to exactly one of 12 labels, at effort none. See spec.md."""
from __future__ import annotations

import re

from harness import entities

CASE_ID = "03"
NAME = "Ticket routing at no reasoning"

LABELS = ["billing", "technical", "account_access", "shipping", "returns", "cancellation", "feature_request",
          "bug_report", "privacy", "partnership", "feedback", "other"]

# (winner, loser): the three tie-break rules of spec.md
RULE_PAIRS = [("billing", "technical"), ("billing", "bug_report"),
              ("cancellation", "billing"), ("cancellation", "returns"),
              ("privacy", "account_access"), ("privacy", "cancellation")]
_RULE_WINNER = {frozenset(p): p[0] for p in RULE_PAIRS}

_MULTI_EXCLUDED = {"other", "feedback", "partnership"}
MULTI_PAIRS = sorted(
    (a, b) for i, a in enumerate(LABELS) for b in LABELS[i + 1:]
    if a not in _MULTI_EXCLUDED and b not in _MULTI_EXCLUDED
    and frozenset((a, b)) not in _RULE_WINNER and {a, b} != {"technical", "bug_report"})

LANG_NAME = {"en": "English", "sv": "Swedish", "de": "German"}

# --------------------------------------------------------------------------- cue pools
# CUES[domain][lang][label] -> decisive phrases. domain "home" = main set, "bike" = shift set (paraphrased).
CUES = {
    "home": {
        "en": {
            "billing": ["charged twice for my Plus subscription", "the invoice shows the wrong amount",
                        "a payment I don't recognise", "my card was charged after the free trial"],
            "technical": ["how do I connect the thermostat to my Wi-Fi", "how do I set up a heating schedule",
                          "can you walk me through pairing the sensors", "where do I change the temperature units"],
            "account_access": ["can't log in to my account", "the password reset email never arrives",
                               "my two-factor code is not accepted", "locked out of my account"],
            "shipping": ["my order still hasn't arrived", "the tracking link hasn't updated in five days",
                         "change the delivery address for my order",
                         "the courier says the parcel was delivered but it isn't here"],
            "returns": ["I'd like to return the motion sensor", "how do I get a return label",
                        "exchange the hub for the white version", "still within the 30-day return window"],
            "cancellation": ["cancel my Plus subscription", "stop the automatic renewal",
                             "end my plan at the end of this month", "I no longer want the subscription"],
            "feature_request": ["please add support for Apple Watch", "it would be great if the app had a dark mode",
                                "could you add a vacation mode", "I wish the app showed humidity graphs"],
            "bug_report": ["the app crashes every time I open the schedule", "error code E42 when I save settings",
                           "the thermostat display freezes", "the hub reboots on its own every night"],
            "privacy": ["delete all my personal data", "what personal data you store about me",
                        "a copy of all the data you hold on me under GDPR",
                        "stop sharing my data with third parties"],
            "partnership": ["become a reseller of your products", "a co-marketing partnership",
                            "integrate your thermostat into our property management platform",
                            "a volume deal for our 200 rental flats"],
            "feedback": ["just wanted to say the new update is fantastic", "the installation was easier than I expected",
                         "honestly I preferred the old app design", "your support team was really helpful last week"],
            "other": ["do you know when the next bus to the airport leaves", "looking for a recipe for cinnamon buns",
                      "is this the right address for the tax office", "who won the hockey game last night",
                      "help me write a poem for my mum's birthday"],
        },
        "sv": {
            "billing": ["dragit pengar två gånger för mitt Plus-abonnemang", "fakturan visar fel belopp",
                        "en debitering jag inte känner igen"],
            "technical": ["hur kopplar jag termostaten till wifi", "hur ställer jag in ett värmeschema",
                          "hjälp att para ihop sensorerna"],
            "account_access": ["kommer inte in på mitt konto", "mejlet för att återställa lösenordet kommer aldrig",
                               "tvåstegskoden godkänns inte"],
            "shipping": ["min beställning har fortfarande inte kommit",
                         "spårningslänken har inte uppdaterats på flera dagar",
                         "ändra leveransadressen för min order"],
            "returns": ["vill returnera rörelsesensorn", "hur får jag en returetikett",
                        "byta hubben mot den vita varianten"],
            "cancellation": ["säga upp mitt Plus-abonnemang", "stänga av den automatiska förnyelsen",
                             "avsluta mitt abonnemang vid månadsskiftet"],
            "feature_request": ["lägg gärna till stöd för Apple Watch", "skulle vara toppen med mörkt läge i appen",
                                "önskar att appen hade ett semesterläge"],
            "bug_report": ["appen kraschar varje gång jag öppnar schemat", "felkod E42 när jag sparar inställningarna",
                           "termostatens skärm fryser"],
            "privacy": ["radera alla mina personuppgifter", "vilka personuppgifter ni lagrar om mig",
                        "en kopia av mina uppgifter enligt GDPR"],
            "partnership": ["bli återförsäljare av era produkter", "ett samarbete kring marknadsföring",
                            "integrera er termostat i vår fastighetsplattform"],
            "feedback": ["ville bara säga att den nya uppdateringen är fantastisk",
                         "installationen var enklare än jag trodde", "er support var jättehjälpsam förra veckan"],
            "other": ["vet ni när nästa buss till flygplatsen går", "letar efter ett recept på kanelbullar",
                      "vem vann hockeymatchen igår"],
        },
        "de": {
            "billing": ["zweimal für mein Plus-Abo abgebucht", "die Rechnung zeigt den falschen Betrag",
                        "eine Abbuchung, die ich nicht kenne"],
            "technical": ["wie verbinde ich das Thermostat mit dem WLAN", "wie richte ich einen Heizplan ein",
                          "Hilfe beim Koppeln der Sensoren"],
            "account_access": ["kann mich nicht in mein Konto einloggen",
                               "die E-Mail zum Zurücksetzen des Passworts kommt nie an",
                               "mein Zwei-Faktor-Code wird nicht akzeptiert"],
            "shipping": ["meine Bestellung ist immer noch nicht angekommen",
                         "die Sendungsverfolgung wurde seit Tagen nicht aktualisiert",
                         "die Lieferadresse meiner Bestellung ändern"],
            "returns": ["möchte den Bewegungssensor zurücksenden", "wie bekomme ich ein Rücksendeetikett",
                        "den Hub gegen die weiße Version umtauschen"],
            "cancellation": ["mein Plus-Abo kündigen", "die automatische Verlängerung stoppen",
                             "mein Abonnement zum Monatsende beenden"],
            "feature_request": ["bitte fügt Unterstützung für die Apple Watch hinzu",
                                "ein Dunkelmodus in der App wäre toll", "ich wünsche mir einen Urlaubsmodus"],
            "bug_report": ["die App stürzt jedes Mal ab, wenn ich den Zeitplan öffne",
                           "Fehlercode E42 beim Speichern der Einstellungen", "das Display des Thermostats friert ein"],
            "privacy": ["alle meine personenbezogenen Daten löschen",
                        "welche personenbezogenen Daten Sie über mich speichern", "eine Kopie meiner Daten nach DSGVO"],
            "partnership": ["Wiederverkäufer Ihrer Produkte werden", "eine gemeinsame Marketingkooperation",
                            "Ihr Thermostat in unsere Hausverwaltungsplattform integrieren"],
            "feedback": ["wollte nur sagen, dass das neue Update fantastisch ist",
                         "die Installation war einfacher als gedacht", "Ihr Support war letzte Woche sehr hilfreich"],
            "other": ["wissen Sie, wann der nächste Bus zum Flughafen fährt", "ich suche ein Rezept für Zimtschnecken",
                      "wer hat gestern das Eishockeyspiel gewonnen"],
        },
        "short": {
            "billing": ["charged twice", "wrong invoice amount"],
            "technical": ["how do I pair sensors", "how to set a schedule"],
            "account_access": ["can't log in", "password reset not working"],
            "shipping": ["where is my order", "parcel still missing"],
            "returns": ["return label please", "want to return this"],
            "cancellation": ["cancel my subscription", "stop auto-renewal"],
            "feature_request": ["please add dark mode", "add Apple Watch support"],
            "bug_report": ["app keeps crashing", "error E42 again"],
            "privacy": ["delete my personal data", "GDPR data request"],
            "partnership": ["reseller partnership inquiry", "interested in reselling"],
            "feedback": ["love the new update", "great support, thanks"],
            "other": ["best pizza in town", "what's the weather tomorrow"],
        },
    },
    "bike": {
        "en": {
            "billing": ["two payments taken for the same month", "the amount on my invoice looks wrong",
                        "a debit from you I can't place", "money taken after my trial ended"],
            "technical": ["how do I link the bike to the rider app", "what's the right way to adjust the assist level",
                          "steps to set up the bike lock in the app",
                          "where can I switch the speed display to miles"],
            "account_access": ["unable to sign in", "the reset link never shows up in my inbox",
                               "the verification code keeps getting rejected",
                               "my account is blocked after too many attempts"],
            "shipping": ["the bike delivery is a week late", "no update on where my delivery is",
                         "deliver to my office instead of my home", "the delivery van never showed up"],
            "returns": ["send the child seat back", "a label to return the helmet",
                        "swap the frame size for a larger one", "still time to send it back under the return policy"],
            "cancellation": ["end my bike subscription", "switch off auto-renew",
                             "close my membership when this month runs out", "I don't want to continue the plan"],
            "feature_request": ["would love a route planner in the app",
                                "any chance you could add a theft alarm notification",
                                "it'd be handy to see battery health over time", "please consider adding Garmin sync"],
            "bug_report": ["the rider app shuts down when I start a ride", "the display shows error 17 and goes blank",
                           "the app's lock button does nothing",
                           "the bike's lights flicker and switch off by themselves"],
            "privacy": ["erase every piece of personal data you have on me",
                        "which personal data you keep about my rides",
                        "a GDPR copy of everything you store about me", "stop passing my location data to partners"],
            "partnership": ["stock your bikes in our shop", "a joint campaign with our cycling club",
                            "partner with our delivery company on a fleet of bikes",
                            "sponsor our city cycling festival"],
            "feedback": ["riding to work has honestly been a joy", "the delivery guy was super friendly",
                         "the new app colours are a step backwards in my opinion",
                         "big thanks to whoever designed the folding pedals"],
            "other": ["know any good hiking trails near Bergen", "how long to boil an egg",
                      "is the pharmacy on your street open on Sundays", "who painted the mural at the train station"],
        },
        "sv": {
            "billing": ["två dragningar för samma månad", "beloppet på fakturan stämmer inte"],
            "technical": ["hur länkar jag cykeln till appen", "hur justerar jag assistansnivån"],
            "account_access": ["går inte att logga in", "verifieringskoden avvisas hela tiden"],
            "shipping": ["cykelleveransen är en vecka sen", "leverera till mitt kontor i stället"],
            "returns": ["skicka tillbaka barnsitsen", "byta till en större ramstorlek"],
            "cancellation": ["säga upp min cykelprenumeration", "stänga av automatisk förlängning"],
            "feature_request": ["en ruttplanerare i appen vore toppen", "lägg till larm vid stöld"],
            "bug_report": ["appen stängs av när jag startar en tur", "displayen visar fel 17 och slocknar"],
            "privacy": ["radera alla personuppgifter ni har om mig", "vilka personuppgifter ni sparar om mina turer"],
            "partnership": ["sälja era cyklar i vår butik", "sponsra vår cykelfestival"],
            "feedback": ["att cykla till jobbet har varit en ren glädje", "budet var supertrevligt"],
            "other": ["några bra vandringsleder nära Åre", "hur länge ska man koka ett ägg"],
        },
        "de": {
            "billing": ["zwei Abbuchungen für denselben Monat", "der Betrag auf meiner Rechnung stimmt nicht"],
            "technical": ["wie verknüpfe ich das Rad mit der App", "wie stelle ich die Unterstützungsstufe ein"],
            "account_access": ["ich komme nicht in mein Konto", "der Bestätigungscode wird ständig abgelehnt"],
            "shipping": ["die Lieferung des Rads ist eine Woche zu spät", "an mein Büro statt nach Hause liefern"],
            "returns": ["den Kindersitz zurückschicken", "auf eine größere Rahmengröße umtauschen"],
            "cancellation": ["mein Fahrrad-Abo kündigen", "die automatische Verlängerung abschalten"],
            "feature_request": ["ein Routenplaner in der App wäre super", "bitte eine Diebstahlwarnung hinzufügen"],
            "bug_report": ["die App schließt sich, sobald ich eine Fahrt starte",
                           "das Display zeigt Fehler 17 und wird schwarz"],
            "privacy": ["alle personenbezogenen Daten über mich löschen",
                        "welche personenbezogenen Daten Sie über meine Fahrten speichern"],
            "partnership": ["Ihre Räder in unserem Laden verkaufen", "unser Radfestival sponsern"],
            "feedback": ["mit dem Rad zur Arbeit zu fahren ist eine Freude", "der Lieferant war super freundlich"],
            "other": ["kennen Sie gute Wanderwege in der Nähe von Garmisch", "wie lange kocht man ein Ei"],
        },
        "short": {
            "billing": ["paid twice this month", "invoice amount wrong"],
            "technical": ["how to link the bike", "adjust assist level how"],
            "account_access": ["unable to sign in", "reset link never arrives"],
            "shipping": ["bike delivery is late", "where's my bike delivery"],
            "returns": ["sending the helmet back", "need a return label"],
            "cancellation": ["end my bike subscription", "switch off auto-renew"],
            "feature_request": ["please add route planning", "add Garmin sync please"],
            "bug_report": ["app shuts down mid-ride", "display shows error 17"],
            "privacy": ["erase my personal data", "GDPR copy of my data"],
            "partnership": ["want to stock your bikes", "fleet partnership proposal"],
            "feedback": ["riding is pure joy", "friendly delivery guy, thanks"],
            "other": ["how long to boil eggs", "good hiking trails nearby"],
        },
    },
}

# Trigger words for the rule labels; must not appear unless that label is a planned issue.
BLACKLIST = {
    "billing": {
        "en": r"\b(charged|charges|invoices?|payments?|paid|pay|paying|billing|billed|refunds?|refunded|debit(ed)?|"
              r"credit card|receipts?|money)\b",
        "sv": r"(betal|debiter|dragning|faktur|återbetal|kvitto|dragit pengar|pengar)",
        "de": r"(bezahl|zahlung|rechnung|abbuch|abgebucht|rückerstatt|belastet|quittung|\bgeld\b)",
    },
    "cancellation": {
        "en": r"\b(cancel\w*|terminat\w*|unsubscrib\w*|auto-?renew\w*)\b|\bend (my|the) (subscription|plan|membership)",
        "sv": r"(säga upp|säger upp|sagt upp|uppsägning|avsluta mitt|avsluta min|förnyelse|förlängning)",
        "de": r"(kündig|stornier|abo beenden|abonnement beenden|verlängerung)",
    },
    "privacy": {
        "en": r"(personal data|personal information|\bgdpr\b|\bmy data\b|data protection|privacy|location data)",
        "sv": r"(personuppgifter|\bgdpr\b|mina uppgifter|integritet|dataskydd)",
        "de": r"(personenbezogen|\bdsgvo\b|datenschutz|meine daten|meiner daten)",
    },
}

ISSUE_BRIEF = {
    "billing": "a problem or question about a charge, payment or invoice",
    "technical": "a how-to question about setting up, connecting or using the product or app (nothing is broken)",
    "account_access": "a problem logging in to their account",
    "shipping": "a question or complaint about the delivery of an order",
    "returns": "wanting to send a physical product back or exchange it",
    "cancellation": "wanting to end their subscription or plan",
    "feature_request": "asking for functionality the product does not have yet",
    "bug_report": "reporting that the product or app malfunctions",
    "privacy": "a request about their personal data",
    "partnership": "a business proposal from another company or organisation",
    "feedback": "sharing an opinion or praise, without asking for any help or action",
    "other": "something completely unrelated to the company's products and services (they wrote to the wrong "
             "place or ask a general question)",
}

DOMAINS = {
    "home": "smart home devices (the {product} smart thermostat, room sensors and a hub) with a companion app and "
            "an optional Plus subscription, sold through its online shop",
    "bike": "e-bikes on a monthly subscription (the {product} e-bike and accessories such as child seats and "
            "helmets) with a rider app, delivered to the customer's door",
}

TONES = ["polite", "frustrated", "terse and to the point", "chatty and friendly", "formal", "anxious",
         "matter-of-fact", "slightly sarcastic"]
CHANNELS = ["an email", "a live chat message", "a web contact form", "an in-app message",
            "a direct message on social media"]


def slices():
    return ["clear", "tie_break", "off_topic", "multi_issue", "very_short", "long", "swedish", "german"]


def slice_weights(variant):
    w = {s: 0.7 / 6 for s in ["clear", "tie_break", "off_topic", "multi_issue", "very_short", "long"]}
    w.update({"swedish": 0.2, "german": 0.1})
    return w


# --------------------------------------------------------------------------- plan / label

def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("‑", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).casefold()


def _pick_issues(rng, difficulty):
    if difficulty == "clear":
        return [rng.choice([lb for lb in LABELS if lb != "other"])]
    if difficulty == "off_topic":
        return ["other"]
    if difficulty == "tie_break":
        w, l = rng.choice(RULE_PAIRS)
        return [l, w] if rng.random() < 0.55 else [w, l]
    if difficulty == "multi_issue":
        a, b = rng.choice(MULTI_PAIRS)
        return [a, b] if rng.random() < 0.5 else [b, a]
    raise ValueError(difficulty)


def plan(rng, slice, variant="main"):
    domain = "home" if variant == "main" else "bike"
    lang, length = "en", "normal"
    if slice in ("clear", "tie_break", "off_topic", "multi_issue"):
        difficulty = slice
    elif slice == "very_short":
        difficulty, length = "very_short", "very_short"
    elif slice == "long":
        difficulty, length = ("clear" if rng.random() < 0.6 else "tie_break"), "long"
    elif slice in ("swedish", "german"):
        lang = "sv" if slice == "swedish" else "de"
        r = rng.random()
        difficulty = "clear" if r < 0.55 else "tie_break" if r < 0.75 else "multi_issue" if r < 0.9 else "off_topic"
    else:
        raise ValueError(slice)
    if difficulty == "very_short":
        issues = [rng.choice(LABELS)]
        pool = CUES[domain]["short"]
    else:
        issues = _pick_issues(rng, difficulty)
        pool = CUES[domain][lang]
    cues = [rng.choice(pool[lb]) for lb in issues]
    brand = rng.choice(entities.companies(pool="main" if variant == "main" else "shift"))["name"]
    product = rng.choice(entities.products())["name"]
    person = rng.choice(entities.people())["name"]
    if length == "very_short":
        words = None
    elif length == "long":
        words = [rng.choice([170, 180, 190, 200]), rng.choice([230, 250, 270])]
    else:
        lo = rng.choice([20, 30, 40, 50])
        words = [lo, lo + rng.choice([30, 40, 50])]
    return {
        "domain": domain, "lang": lang, "difficulty": difficulty, "length": length, "words": words,
        "issues": issues, "cues": cues, "brand": brand, "product": product, "customer": person,
        "tone": rng.choice(TONES), "channel": rng.choice(CHANNELS),
        "greeting": rng.random() < 0.6, "signoff": rng.random() < 0.6,
        "order_number": f"#{rng.randint(100000, 999999)}" if rng.random() < 0.3 else None,
        "typos": lang == "en" and rng.random() < 0.25,
    }


def label(plan):
    issues = plan["issues"]
    if len(issues) == 1:
        return issues[0]
    a, b = issues
    return _RULE_WINNER.get(frozenset((a, b)), a)


# --------------------------------------------------------------------------- generate / verify

def _forbidden(plan) -> list[str]:
    out = []
    if "billing" not in plan["issues"]:
        out.append("payments, charges, prices, money, invoices or refunds")
    if "cancellation" not in plan["issues"]:
        out.append("cancelling or ending anything, or subscription renewal")
    if "privacy" not in plan["issues"]:
        out.append("personal data, privacy or GDPR")
    return out


def generator_prompt(plan):
    lang = LANG_NAME[plan["lang"]]
    domain = DOMAINS[plan["domain"]].format(product=plan["product"])
    lines = [f"Write one customer message sent to the support desk of {plan['brand']}, a company that sells {domain}.",
             "", f"- Language: {lang}.", f"- Form: {plan['channel']}. Tone: {plan['tone']}."]
    if plan["length"] == "very_short":
        lines.append("- Length: 3 to 7 words in total (strictly fewer than 8 words). One line. No greeting, no "
                     "signature, no name.")
    elif plan["length"] == "long":
        lines.append(f"- Length: {plan['words'][0]} to {plan['words'][1]} words. Include a lot of rambling "
                     "background (their home or commute, family, how long they have been a customer, what they "
                     "tried) that raises no additional problem or request.")
    else:
        lines.append(f"- Length: {plan['words'][0]} to {plan['words'][1]} words.")
    if plan["length"] != "very_short":
        lines.append(f"- {'Open with a short greeting.' if plan['greeting'] else 'No greeting; start directly.'} "
                     + (f"Sign off with the name {plan['customer']}." if plan['signoff'] else "No signature."))
        if plan["order_number"] and plan["difficulty"] != "off_topic":
            lines.append(f"- Mention the order or customer number {plan['order_number']}.")
    if plan["typos"]:
        lines.append("- Include one or two small, natural typos elsewhere in the message (never inside the "
                     "required phrases).")
    issues, cues = plan["issues"], plan["cues"]
    if len(issues) == 1:
        lines += ["", f"Content: the customer's only point is {ISSUE_BRIEF[issues[0]]}.",
                  f'The message MUST contain this exact phrase, character for character (only its first letter may '
                  f'change case): "{cues[0]}"']
    else:
        lines += ["", "Content: the customer raises exactly two points, both genuine and both clearly expressed, "
                  "in this order:",
                  f"1. {ISSUE_BRIEF[issues[0]]}; it MUST contain this exact phrase: \"{cues[0]}\"",
                  f"2. {ISSUE_BRIEF[issues[1]]}; it MUST contain this exact phrase: \"{cues[1]}\"",
                  "Copy each phrase character for character (only its first letter may change case), and the first "
                  "phrase must appear before the second."]
    lines.append("Do not raise any other problem, question or request.")
    forb = _forbidden(plan)
    if forb:
        lines.append("Do not mention " + "; nor ".join(forb) + ".")
    if issues == ["other"]:
        lines.append(f"The message must have nothing to do with {plan['brand']}'s products, orders, account or "
                     "services.")
    lines += ["", "Output only the message text: no subject line, no quotation marks around it, no notes."]
    return "\n".join(lines)


def make_input(plan, text):
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'“" and t[-1] in "\"'”":
        t = t[1:-1].strip()
    return t


def verify(plan, text):
    t = _norm(text)
    pos = []
    for c in plan["cues"]:
        i = t.find(_norm(c))
        if i < 0:
            return False, f"cue missing: {c!r}"
        pos.append(i)
    if pos != sorted(pos):
        return False, "cues out of planned order"
    domain = plan["domain"]
    for pool in CUES[domain].values():
        for lb, cs in pool.items():
            if lb in plan["issues"]:
                continue
            for c in cs:
                if len(c) >= 12 and _norm(c) in t:
                    return False, f"cue of unplanned label {lb}: {c!r}"
    # blank out the planned cues before checking trigger words (a cue may itself contain one)
    tb = t
    for c in plan["cues"]:
        tb = tb.replace(_norm(c), " ")
    for lb, pats in BLACKLIST.items():
        if lb in plan["issues"]:
            continue
        for lang in {plan["lang"], "en"}:
            m = re.search(pats[lang], tb)
            if m:
                return False, f"trigger word for unplanned {lb}: {m.group(0)!r}"
    n = len(text.split())
    if plan["length"] == "very_short" and n >= 8:
        return False, f"very_short has {n} words"
    if plan["length"] == "long" and n <= 150:
        return False, f"long has only {n} words"
    return True, ""


_DEFS = """Labels:
- billing: charges, payments, invoices, receipts, prices, payment methods, refunds of charges
- technical: help setting up, connecting, configuring or using the product, app or website (nothing is broken)
- account_access: login problems, passwords, two-factor codes, locked or blocked accounts
- shipping: delivery of an order: tracking, delays, delivery address, parcels that have not arrived
- returns: sending a product back, return labels, exchanges, the return window
- cancellation: ending a subscription or plan, stopping automatic renewal
- feature_request: asking for functionality the product does not have
- bug_report: the product, app or website malfunctions: crashes, error codes, freezes, features that stop working
- privacy: personal data: what is stored, copies of data, deletion of personal data, sharing, GDPR requests
- partnership: business proposals: reselling, co-marketing, integrations, sponsorship, volume deals
- feedback: opinions, praise or complaints with no request for help or action
- other: anything unrelated to the company's products and services
Tie-break rules: (1) billing beats technical and bug_report when a payment, charge or invoice is mentioned;
(2) cancellation beats billing and returns when the customer wants to end a subscription; (3) privacy beats
account_access and cancellation when the customer asks about or wants deletion of their personal data.
If several issues are raised and no rule applies, the issue mentioned first wins."""


def verifier_brief(plan):
    exp = label(plan)
    if len(plan["issues"]) == 1:
        what = (f"The message raises exactly one issue, of type '{plan['issues'][0]}' (decisive phrase: "
                f"\"{plan['cues'][0]}\").")
        change = ("It would change the answer if the message also raised a second issue matching another label, "
                  "or if the message could reasonably be routed to a different label.")
    else:
        a, b = plan["issues"]
        what = (f"The message raises exactly two issues, in this order: first '{a}' (phrase \"{plan['cues'][0]}\"), "
                f"then '{b}' (phrase \"{plan['cues'][1]}\"). The two issues being present is intended; the rules "
                f"above resolve them to '{exp}'.")
        change = ("It would change the answer if a third issue matching another label appeared, if either planned "
                  "issue were missing or not a genuine request, or if the order of the two issues were reversed.")
    return (f"A customer support message is routed to exactly one of 12 labels.\n{_DEFS}\n\n{what}\n"
            f"Correct label: {exp}.\n{change}")


# --------------------------------------------------------------------------- parse / score

def parse(output, settings, item):
    if isinstance(output, list):
        output = output[0] if output else {}
    output = output or {}
    return {"text": output.get("text") or "", "refusal": output.get("refusal")}


def _label_word(s: str) -> bool:
    low = s.lower()
    return any(re.search(rf"(?<![a-z_]){lb}(?![a-z_])", low) or lb.replace("_", " ") in low for lb in LABELS)


def score(expected, parsed):
    parsed = parsed if isinstance(parsed, dict) else {"text": parsed if isinstance(parsed, str) else ""}
    raw = parsed.get("text") or ""
    p = raw.strip()
    valid = p in LABELS
    passed = p == expected
    nonanswer = bool(parsed.get("refusal")) or not p or "?" in p or not _label_word(p)
    if passed:
        cats = []
    elif nonanswer:
        cats = ["nonanswer"]
    elif not valid:
        cats = ["format"]
    elif expected == "other":
        cats = ["missed_other"]
    elif p == "other":
        cats = ["false_other"]
    else:
        cats = ["wrong_label"]
    sec = {"expected_idx": LABELS.index(expected) if expected in LABELS else -1,
           "predicted_idx": LABELS.index(p) if valid else -1}
    return {"passed": passed, "valid": valid, "nonanswer": nonanswer and not passed, "secondary": sec,
            "categories": cats, "diff": "" if passed else f"expected {expected!r}, got {raw[:80]!r}"}


def macro_f1(pairs):
    """pairs: (expected_idx, predicted_idx); predicted -1 = invalid. Mean F1 over labels seen in either column."""
    seen = {e for e, _ in pairs} | {p for _, p in pairs if p >= 0}
    if not seen:
        return 0.0
    f1s = []
    for k in seen:
        tp = sum(1 for e, p in pairs if e == k and p == k)
        fp = sum(1 for e, p in pairs if e != k and p == k)
        fn = sum(1 for e, p in pairs if e == k and p != k)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s)


def aggregate(rows):
    pairs = [(int(r["secondary"]["expected_idx"]), int(r["secondary"]["predicted_idx"]))
             for r in rows if (r.get("secondary") or {}).get("expected_idx", -1) >= 0]
    n = len(rows)
    return {"macro_f1": macro_f1(pairs),
            "nonanswer_rate": sum(bool(r.get("nonanswer")) for r in rows) / n if n else 0.0,
            "validity": sum(bool(r.get("valid")) for r in rows) / n if n else 0.0,
            "rows_scored_for_f1": len(pairs)}


def failure_taxonomy():
    return ["nonanswer", "format", "wrong_label", "missed_other", "false_other", "other"]


def answer_strings(expected):
    return []  # the label names are part of the task definition and must appear in any prompt


def port_settings(settings):
    # The Responses API rejects max_output_tokens below 16; a 5-token cap cannot survive the port.
    if settings.get("max_output_tokens") and settings["max_output_tokens"] < 16:
        settings["max_output_tokens"] = 16
    return settings


def legacy_markers():
    return [r"Output ONLY the label", r"\bNEVER\b", r"\bALWAYS\b", r"^IMPORTANT:", r"Tie-break rules"]
