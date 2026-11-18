"""Case 02: invoice fields with a confidence flag (see spec.md).

Plan-first: the plan samples every field value and its written form, a code template renders a draft invoice
from it, and the generator rewrites the draft in a given layout and style while keeping every value string
verbatim. The label is the sampled values. Review flags come from token logprobs (legacy) or one of the
non-logprob methods the optimiser may choose.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache

from harness import entities

CASE_ID = "02"
NAME = "Invoice fields with a confidence flag"
SCHEMA_NAME = "invoice_fields"

FIELDS = ["vendor", "invoice_number", "issue_date", "due_date", "currency", "net", "vat", "total"]
AMOUNT_FIELDS = ("net", "vat", "total")
DATE_FIELDS = ("issue_date", "due_date")
FLAG_METHODS = ["logprob", "none", "null_when_unsure", "confidence_field", "two_run_agreement"]
SLICES = ["date_formats", "decimal_comma", "missing_field", "subtotal_vs_total", "mixed_currencies", "swedish",
          "german"]

# --------------------------------------------------------------------------- reference tables

HOME_CURRENCY = {"Sweden": "SEK", "Germany": "EUR", "United Kingdom": "GBP", "United States": "USD",
                 "Norway": "NOK", "Finland": "EUR", "Denmark": "DKK", "France": "EUR", "Netherlands": "EUR",
                 "Switzerland": "CHF"}
VAT_RATE = {"Sweden": "25", "Germany": "19", "United Kingdom": "20", "United States": "7", "Norway": "25",
            "Finland": "25.5", "Denmark": "25", "France": "20", "Netherlands": "21", "Switzerland": "8.1"}
PER_EUR = {"EUR": Decimal("1"), "SEK": Decimal("11.2"), "USD": Decimal("1.08"), "GBP": Decimal("0.86"),
           "NOK": Decimal("11.6"), "DKK": Decimal("7.46"), "CHF": Decimal("0.94")}
CITIES = {"Sweden": ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Linköping", "Örebro"],
          "Germany": ["Berlin", "Hamburg", "München", "Köln", "Frankfurt am Main", "Leipzig"],
          "United Kingdom": ["London", "Manchester", "Leeds", "Bristol", "Edinburgh"],
          "United States": ["Chicago", "Austin", "Denver", "Boston", "Seattle"],
          "Norway": ["Oslo", "Bergen", "Trondheim"], "Finland": ["Helsinki", "Tampere", "Turku"],
          "Denmark": ["Copenhagen", "Aarhus", "Odense"], "France": ["Paris", "Lyon", "Lille"],
          "Netherlands": ["Amsterdam", "Rotterdam", "Utrecht"], "Switzerland": ["Zurich", "Basel", "Bern"]}
_CITY_NAMES = {x for v in CITIES.values() for x in v}  # e.g. an invented company called "Boston" is never used
CURRENCY_CODES = ["EUR", "SEK", "USD", "GBP", "CHF", "NOK", "DKK"]
SYMBOL_OF = {"EUR": "€", "GBP": "£", "USD": "$", "SEK": "kr"}

EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
EN_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SV_MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
             "november", "december"]
DE_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
             "November", "Dezember"]

LABELS = {
    "en": {"invoice": "INVOICE", "from": "From", "bill_to": "Bill to", "invoice_number": "Invoice no.",
           "issue_date": "Invoice date", "due_date": "Due date", "delivery": "Delivery date",
           "po": "Your order no.", "subtotal": "Subtotal", "discount": "Discount", "net": "Net amount",
           "vat": "VAT", "sales_tax": "Sales tax", "total": "Total", "total_gross": "Total incl. VAT",
           "currency": "Currency", "item": "Description", "amount": "Amount",
           "info": "For information only: the total corresponds to approx.",
           "info_note": "Invoice currency is {cur}; please pay in {cur}."},
    "sv": {"invoice": "FAKTURA", "from": "Från", "bill_to": "Kund", "invoice_number": "Fakturanummer",
           "issue_date": "Fakturadatum", "due_date": "Förfallodatum", "delivery": "Leveransdatum",
           "po": "Er referens", "subtotal": "Delsumma", "discount": "Rabatt", "net": "Belopp exkl. moms",
           "vat": "Moms", "sales_tax": "Moms", "total": "Att betala", "total_gross": "Att betala inkl. moms",
           "currency": "Valuta", "item": "Beskrivning", "amount": "Belopp",
           "info": "Endast för information: totalbeloppet motsvarar ca",
           "info_note": "Fakturavaluta är {cur}; betala i {cur}."},
    "de": {"invoice": "RECHNUNG", "from": "Von", "bill_to": "Rechnungsempfänger", "invoice_number": "Rechnungsnummer",
           "issue_date": "Rechnungsdatum", "due_date": "Zahlbar bis", "delivery": "Lieferdatum",
           "po": "Ihre Bestellnummer", "subtotal": "Zwischensumme", "discount": "Rabatt", "net": "Nettobetrag",
           "vat": "MwSt.", "sales_tax": "MwSt.", "total": "Gesamtbetrag", "total_gross": "Gesamtbetrag inkl. MwSt.",
           "currency": "Währung", "item": "Beschreibung", "amount": "Betrag",
           "info": "Nur zur Information: der Gesamtbetrag entspricht ca.",
           "info_note": "Rechnungswährung ist {cur}; bitte in {cur} zahlen."},
}
LANG_NAME = {"en": "English", "sv": "Swedish", "de": "German"}

SERVICE_WORDS = {
    "en": ["licence", "support plan", "installation", "consulting hours", "maintenance", "spare parts", "training",
           "hosting", "delivery", "service fee"],
    "sv": ["licens", "supportavtal", "installation", "konsulttimmar", "underhåll", "reservdelar", "utbildning",
           "drift", "frakt", "serviceavgift"],
    "de": ["Lizenz", "Supportvertrag", "Installation", "Beratungsstunden", "Wartung", "Ersatzteile", "Schulung",
           "Hosting", "Versand", "Servicegebühr"],
}

MAIN_TEMPLATES = ["classic", "kv_list", "email", "pipe_table", "receipt", "letter", "dot_leaders",
                  "summary_first", "footer_header", "export_rules", "portal_notice", "ascii_box"]
SHIFT_TEMPLATES = ["edi_dump", "fax_cover", "statement_narrative"]
TEMPLATE_STYLE = {
    "classic": "a classic plain-text invoice as copied out of a PDF: vendor block at the top, customer block, "
               "invoice details, a list of line items and a totals block at the bottom",
    "kv_list": "a compact list of 'Label: value' lines, one fact per line, as an accounting system prints it",
    "email": "an e-mail from the vendor's accounts team to the customer that gives the invoice details in the "
             "body in short sentences and a few lines (no subject line, no attachments mentioned by file name)",
    "pipe_table": "a plain-text invoice whose line items and totals are laid out in a table with '|' column "
                  "separators",
    "receipt": "a narrow receipt-style printout with short centred lines and the totals at the bottom",
    "letter": "a formal business letter: sender address block, recipient address block, a short paragraph "
              "stating the invoice, then the figures",
    "dot_leaders": "a two-column layout where each label is followed by dot leaders and the value, e.g. "
                   "'Label ........ value'",
    "summary_first": "an invoice that starts with a short summary box (amount to pay, due date if any) and gives "
                     "the full details below it",
    "footer_header": "an unusual layout where the line items and totals come first and the invoice details "
                     "(number, dates, parties) are printed in a footer at the end",
    "export_rules": "a plain-text export from an ERP system with '=====' rules between sections and upper-case "
                    "section headings",
    "portal_notice": "the text of an e-invoicing portal notification that lists the invoice fields received "
                     "from the supplier",
    "ascii_box": "an invoice drawn with ASCII box characters (+-----+ and |) around the header and the totals",
    "edi_dump": "a raw semicolon-separated export, a few long lines of 'key=value;' segments with terse "
                "abbreviated keys, as dumped from an EDI gateway",
    "fax_cover": "a faxed invoice: a fax cover header (to, from, pages) followed by the invoice, with irregular "
                 "spacing as if typed on an old form",
    "statement_narrative": "a narrative supplier statement that opens with the amount payable and explains the "
                           "invoice in a running paragraph, with the remaining details at the end",
}

# --------------------------------------------------------------------------- formatting helpers

D2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x).quantize(D2, rounding=ROUND_HALF_UP)


def fmt_amount(x: Decimal, style: str) -> str:
    """en '1,234.50'; plain_dot '1234.50'; de '1.234,50'; sv '1 234,50'; plain_comma '1234,50'."""
    s = f"{q2(x):.2f}"
    ip, dp = s.split(".")
    neg = ip.startswith("-")
    ip = ip.lstrip("-")
    groups = []
    while len(ip) > 3:
        groups.insert(0, ip[-3:])
        ip = ip[:-3]
    groups.insert(0, ip)
    sep = {"en": ",", "de": ".", "sv": " ", "plain_dot": "", "plain_comma": ""}[style]
    dec = "." if style in ("en", "plain_dot") else ","
    return ("-" if neg else "") + sep.join(groups) + dec + dp


def fmt_date(d: date, fmt: str) -> str:
    dd, mm, yy = d.day, d.month, d.year
    return {
        "iso": f"{yy:04d}-{mm:02d}-{dd:02d}",
        "dmy_dot": f"{dd:02d}.{mm:02d}.{yy}",
        "dmy_slash": f"{dd:02d}/{mm:02d}/{yy}",
        "d_mon_y": f"{dd} {EN_MON[mm - 1]} {yy}",
        "d_month_y": f"{dd} {EN_MONTHS[mm - 1]} {yy}",
        "month_d_y": f"{EN_MONTHS[mm - 1]} {dd}, {yy}",
        "d_mon_y_dash": f"{dd:02d}-{EN_MON[mm - 1]}-{yy}",
        "dmy_dot_short": f"{dd:02d}.{mm:02d}.{yy % 100:02d}",
        "dmy_slash_short": f"{dd:02d}/{mm:02d}/{yy % 100:02d}",
        "d_nopad_dot": f"{dd}.{mm}.{yy}",
        "ordinal": f"{dd}{_ordinal(dd)} {EN_MONTHS[mm - 1]} {yy}",
        "sv_d_month_y": f"{dd} {SV_MONTHS[mm - 1]} {yy}",
        "de_d_month_y": f"{dd}. {DE_MONTHS[mm - 1]} {yy}",
    }[fmt]


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# --------------------------------------------------------------------------- interface: slices

def slices():
    return list(SLICES)


def shift_slices():
    return list(SLICES)


def slice_weights(variant):
    w = {s: 0.14 for s in SLICES}
    w["swedish"] = 0.20
    w["german"] = 0.10
    return w


# --------------------------------------------------------------------------- plan

def _pick_company(rng, pool, country=None, exclude=()):
    cs = [c for c in entities.companies(pool) if (country is None or c["country"] == country)
          and c["legal_name"] not in exclude and c["name"] not in _CITY_NAMES]
    return rng.choice(cs)


def _invoice_number(rng) -> str:
    k = rng.randrange(7)
    if k == 0:
        return f"INV-2026-{rng.randint(1, 9999):04d}"
    if k == 1:
        return f"F26-{rng.randint(100, 99999):05d}"
    if k == 2:
        return f"RE-{rng.randint(10000, 999999)}"
    if k == 3:
        return str(rng.randint(1000000, 9999999))
    if k == 4:
        return f"SI{rng.randint(10000, 99999)}"
    if k == 5:
        return f"{rng.choice('ABCDEFGHKMNPRSTV')}-{rng.randint(1000, 9999)}-26"
    return f"{rng.randint(26000, 26999)}/{rng.randint(10, 99)}"


def _po_ref(rng) -> str:
    return rng.choice([f"PO-{rng.randint(10000, 99999)}", f"ORD{rng.randint(100000, 999999)}",
                       f"BEST-{rng.randint(1000, 9999)}", f"K{rng.randint(1000, 9999)}-{rng.choice('ABCDEFG')}"])


def _split_amount(rng, total: Decimal, k: int) -> list[Decimal]:
    if k == 1:
        return [total]
    cents = int(total * 100)
    w = [rng.uniform(1, 4) for _ in range(k)]
    parts = [int(cents * x / sum(w)) for x in w[:-1]]
    parts.append(cents - sum(parts))
    return [Decimal(c) / 100 for c in parts]


def plan(rng, slice, variant="main"):
    pool = "shift" if variant == "shift" else "main"
    lang = {"swedish": "sv", "german": "de"}.get(slice, "en")
    country = {"sv": "Sweden", "de": "Germany"}.get(lang)
    vendor = _pick_company(rng, pool, country)
    buyer = _pick_company(rng, pool, rng.choice([None, vendor["country"]]), exclude=(vendor["legal_name"],))
    vc = vendor["country"]

    # currency
    home = HOME_CURRENCY[vc]
    if lang == "sv":
        currency = "SEK" if rng.random() < 0.8 else "EUR"
    elif lang == "de":
        currency = "EUR"
    else:
        currency = home if rng.random() < 0.75 else rng.choice([c for c in ("EUR", "USD", "GBP") if c != home])
    styles = ["code_prefix", "code_suffix", "header"]
    if currency in ("EUR", "GBP", "USD"):
        styles += ["symbol"] * 2
    if currency == "SEK":
        styles += ["kr"] * (3 if lang == "sv" else 1)
    if lang == "de" and currency == "EUR":
        styles += ["symbol"] * 2
    currency_style = rng.choice(styles)
    if currency_style == "symbol":
        currency_surface = SYMBOL_OF[currency]
    elif currency_style == "kr":
        currency_surface = "kr"
    else:
        currency_surface = currency

    # amounts
    if lang == "sv":
        amount_style = rng.choice(["sv", "sv", "plain_comma"])
    elif lang == "de":
        amount_style = "de"
    elif slice == "decimal_comma":
        amount_style = rng.choice(["de", "sv", "plain_comma"])
    else:
        amount_style = rng.choice(["en", "en", "plain_dot"])
    mag = rng.choice([2, 3, 3, 4, 4])
    base = Decimal(rng.randint(10 ** mag, 6 * 10 ** mag)) + Decimal(rng.choice([0, 0, rng.randint(1, 99)])) / 100
    rate = Decimal(VAT_RATE[vc])
    subtotal = discount = None
    if slice == "subtotal_vs_total":
        subtotal = q2(base)
        pct = rng.choice([5, 10, 15, 20])
        discount = q2(subtotal * pct / 100)
        net = subtotal - discount
    else:
        pct = None
        net = q2(base)
    vat = q2(net * rate / 100)
    total = net + vat

    # dates
    issue = date(2026, 1, 5) + timedelta(days=rng.randint(0, 314))
    due = issue + timedelta(days=rng.choice([10, 14, 15, 20, 30, 30, 45, 60]))
    delivery = None
    if slice == "date_formats":
        if rng.random() < 0.5:  # make numeric day-first dates genuinely ambiguous
            issue = date(2026, rng.randint(1, 10), rng.randint(1, 12))
            due = issue + timedelta(days=rng.choice([10, 14, 20, 30]))
        hard = ["dmy_slash", "dmy_slash", "dmy_slash_short", "dmy_dot_short", "month_d_y", "d_mon_y_dash",
                "d_nopad_dot", "ordinal", "d_month_y"]
        issue_fmt, due_fmt = rng.choice(hard), rng.choice(hard)
        if rng.random() < 0.5:
            delivery = issue - timedelta(days=rng.randint(1, 9))
    elif lang == "sv":
        issue_fmt = rng.choice(["iso", "iso", "sv_d_month_y", "dmy_dot"])
        due_fmt = issue_fmt if rng.random() < 0.7 else rng.choice(["iso", "sv_d_month_y"])
    elif lang == "de":
        issue_fmt = rng.choice(["dmy_dot", "dmy_dot", "de_d_month_y", "dmy_dot_short"])
        due_fmt = issue_fmt if rng.random() < 0.7 else rng.choice(["dmy_dot", "de_d_month_y"])
    else:
        issue_fmt = rng.choice(["iso", "d_mon_y", "d_month_y", "dmy_dot"])
        due_fmt = issue_fmt if rng.random() < 0.7 else rng.choice(["iso", "d_mon_y", "d_month_y", "dmy_dot"])
    delivery_fmt = rng.choice(["dmy_slash", "d_mon_y", "iso"]) if delivery else None

    missing: list[str] = []
    if slice == "missing_field":
        missing = rng.choice([["due_date"], ["due_date"], ["invoice_number"], ["net", "vat"],
                              ["due_date", "invoice_number"], ["issue_date"]])
    inv_no = _invoice_number(rng)
    po = _po_ref(rng) if ("invoice_number" not in missing and rng.random() < 0.35) else None

    lines = []
    if "net" not in missing:
        k = rng.choice([1, 2, 2, 3, 3, 4])
        target = subtotal if subtotal is not None else net
        prods = rng.sample(entities.products(), k)
        words = rng.sample(SERVICE_WORDS[lang], k)
        for amt, pr, w in zip(_split_amount(rng, target, k), prods, words):
            lines.append({"desc": f"{pr['name']} {w}", "amount": fmt_amount(amt, amount_style)})

    info = None
    if slice == "mixed_currencies":
        other = rng.choice([c for c in CURRENCY_CODES if c not in (currency, home)] if currency != home
                           else [c for c in CURRENCY_CODES if c != currency])
        if currency != home and rng.random() < 0.6:
            other = home  # the vendor's home currency shown for information is the classic trap
        conv = q2(total / PER_EUR[currency] * PER_EUR[other])
        info = {"currency": other, "amount": fmt_amount(conv, amount_style)}

    templates = SHIFT_TEMPLATES if variant == "shift" else MAIN_TEMPLATES
    p = {
        "lang": lang, "template": rng.choice(templates),
        "vendor": vendor["legal_name"], "vendor_name": vendor["name"], "vendor_city": rng.choice(CITIES[vc]),
        "vendor_country": vc, "buyer": buyer["legal_name"], "buyer_name": buyer["name"],
        "buyer_city": rng.choice(CITIES[buyer["country"]]),
        "invoice_number": inv_no, "po_ref": po,
        "issue_date": issue.isoformat(), "issue_surface": fmt_date(issue, issue_fmt),
        "due_date": due.isoformat(), "due_surface": fmt_date(due, due_fmt),
        "delivery_surface": fmt_date(delivery, delivery_fmt) if delivery else None,
        "currency": currency, "currency_style": currency_style, "currency_surface": currency_surface,
        "amount_style": amount_style, "vat_rate": VAT_RATE[vc], "tax_label": "sales_tax" if vc == "United States" else "vat",
        "net": f"{net:.2f}", "vat": f"{vat:.2f}", "total": f"{total:.2f}",
        "net_surface": fmt_amount(net, amount_style), "vat_surface": fmt_amount(vat, amount_style),
        "total_surface": fmt_amount(total, amount_style),
        "subtotal_surface": fmt_amount(subtotal, amount_style) if subtotal is not None else None,
        "discount_surface": fmt_amount(discount, amount_style) if discount is not None else None,
        "discount_pct": pct, "lines": lines, "info": info, "missing": missing,
        "style": {"caps_headings": rng.random() < 0.5, "density": rng.choice(["compact", "airy"]),
                  "extras": rng.sample(["street address", "phone number", "e-mail address", "closing line",
                                        "bank name (no account number)", "vendor website"], 2)},
        "noise_seed": rng.randint(0, 10 ** 9) if variant == "shift" else None,
    }
    return p


# --------------------------------------------------------------------------- label

def label(plan):
    out = {
        "vendor": plan["vendor"], "invoice_number": plan["invoice_number"], "issue_date": plan["issue_date"],
        "due_date": plan["due_date"], "currency": plan["currency"], "net": plan["net"], "vat": plan["vat"],
        "total": plan["total"],
    }
    for f in plan.get("missing") or []:
        out[f] = None
    return out


# --------------------------------------------------------------------------- draft rendering

def _money(plan, surface: str) -> str:
    st, cs = plan["currency_style"], plan["currency_surface"]
    if st == "header":
        return surface
    if st == "code_prefix":
        return f"{cs} {surface}"
    if st == "code_suffix" or st == "kr":
        return f"{surface} {cs}"
    # symbol: prefix in English, suffix otherwise
    return f"{cs}{surface}" if plan["lang"] == "en" else f"{surface} {cs}"


def _fields(plan) -> dict:
    """Ordered blocks of (label, value) for the templates."""
    L = LABELS[plan["lang"]]
    miss = set(plan["missing"])
    meta = []
    if "invoice_number" not in miss:
        meta.append((L["invoice_number"], plan["invoice_number"]))
    if "issue_date" not in miss:
        meta.append((L["issue_date"], plan["issue_surface"]))
    if plan["delivery_surface"]:
        meta.append((L["delivery"], plan["delivery_surface"]))
    if "due_date" not in miss:
        meta.append((L["due_date"], plan["due_surface"]))
    if plan["po_ref"]:
        meta.append((L["po"], plan["po_ref"]))
    if plan["currency_style"] == "header":
        meta.append((L["currency"], plan["currency_surface"]))
    lines = [(ln["desc"], ln["amount"]) for ln in plan["lines"]]
    tot = []
    if plan["subtotal_surface"]:
        tot.append((L["subtotal"], plan["subtotal_surface"]))
        tot.append((f"{L['discount']} {plan['discount_pct']}%", "-" + plan["discount_surface"]))
    if "net" not in miss:
        tot.append((L["net"], _money(plan, plan["net_surface"])))
    if "vat" not in miss:
        rate = plan["vat_rate"] if plan["lang"] == "en" else plan["vat_rate"].replace(".", ",")
        tot.append((f"{L[plan['tax_label']]} {rate}%", _money(plan, plan["vat_surface"])))
    tot.append((L["total"] if "net" not in miss else L["total_gross"], _money(plan, plan["total_surface"])))
    info = []
    if plan["info"]:
        info.append(f"{L['info']} {plan['info']['currency']} {plan['info']['amount']}. "
                    + L["info_note"].format(cur=plan["currency"]))
    return {"L": L, "meta": meta, "lines": lines, "totals": tot, "info": info}


def _kv(pairs, sep=": "):
    return [f"{a}{sep}{b}" for a, b in pairs]


def render_draft(plan) -> str:
    f = _fields(plan)
    L, meta, lines, tot, info = f["L"], f["meta"], f["lines"], f["totals"], f["info"]
    vend = [plan["vendor"], plan["vendor_city"]]
    buy = [f"{L['bill_to']}: {plan['buyer']}", plan["buyer_city"]]
    t = plan["template"]
    out: list[str] = []
    if t in ("classic", "letter", "fax_cover"):
        if t == "fax_cover":
            out += ["FAX", f"To: {plan['buyer']}", f"From: {plan['vendor']}", "Pages: 1", ""]
        out += vend + [""] + buy + ["", L["invoice"]] + _kv(meta) + [""]
        if t == "letter":
            out += [f"{plan['buyer']} is invoiced as follows."]
        out += _kv(lines, "   ") + [""] + _kv(tot, "   ") + info
    elif t in ("kv_list", "portal_notice"):
        if t == "portal_notice":
            out += ["New e-invoice received", ""]
        out += _kv([(L["from"], plan["vendor"]), (L["bill_to"], plan["buyer"])] + meta + lines + tot) + info
    elif t == "email":
        out += [f"{plan['buyer']},", "", f"{L['invoice']} — {plan['vendor']}"] + _kv(meta) + [""]
        out += _kv(lines, " — ") + _kv(tot) + info + ["", plan["vendor"]]
    elif t in ("pipe_table", "ascii_box"):
        bar = "+" + "-" * 44 + "+"
        out += [plan["vendor"], plan["vendor_city"], "", *buy, ""]
        out += ([bar] if t == "ascii_box" else []) + [f"| {a} | {b} |" for a, b in meta] + ([bar] if t == "ascii_box" else [])
        out += [f"| {L['item']} | {L['amount']} |"] + [f"| {a} | {b} |" for a, b in lines]
        out += ([bar] if t == "ascii_box" else []) + [f"| {a} | {b} |" for a, b in tot] + ([bar] if t == "ascii_box" else []) + info
    elif t == "receipt":
        out += [plan["vendor"], plan["vendor_city"],
                "-" * 24] + _kv(meta) + ["-" * 24] + _kv(lines, "  ") + ["-" * 24] + _kv(tot, "  ") + info + buy
    elif t == "dot_leaders":
        out += vend + buy + [""] + [f"{a} ........ {b}" for a, b in meta + lines + tot] + info
    elif t in ("summary_first", "statement_narrative"):
        top = [p for p in tot if p[0].startswith((L["total"], L["total_gross"]))]
        due = [p for p in meta if p[0] == L["due_date"]]
        out += [L["invoice"], *_kv(top + due), "", plan["vendor"], *buy, ""] + _kv(meta) + _kv(lines) + _kv(tot) + info
    elif t == "footer_header":
        out += _kv(lines, "  ") + _kv(tot, "  ") + info + ["", "---"] + vend + buy + _kv(meta)
    elif t == "export_rules":
        rule = "=" * 30
        out += [rule, L["invoice"], rule, plan["vendor"], *buy, rule] + _kv(meta) + [rule] + _kv(lines) + [rule] + _kv(tot) + info
    elif t == "edi_dump":
        segs = [f"SUPPLIER={plan['vendor']}", f"BUYER={plan['buyer']}"] + [f"{a}={b}" for a, b in meta]
        out += [";".join(segs) + ";", ";".join(f"LINE={a}={b}" for a, b in lines) + ";",
                ";".join(f"{a}={b}" for a, b in tot) + ";"] + info
    else:
        raise ValueError(f"unknown template {t}")
    return "\n".join(out)


# --------------------------------------------------------------------------- generator

def verbatim_strings(plan) -> list[tuple[str, str]]:
    """(role, string) pairs that must appear verbatim in the item text."""
    miss = set(plan["missing"])
    out = [("vendor (the issuer)", plan["vendor"]), ("customer (bill-to)", plan["buyer"])]
    if "invoice_number" not in miss:
        out.append(("invoice number", plan["invoice_number"]))
    if "issue_date" not in miss:
        out.append(("invoice date", plan["issue_surface"]))
    if "due_date" not in miss:
        out.append(("due date", plan["due_surface"]))
    if plan["delivery_surface"]:
        out.append(("delivery date", plan["delivery_surface"]))
    if plan["po_ref"]:
        out.append(("customer's order number", plan["po_ref"]))
    out.append(("currency", plan["currency_surface"]))
    for ln in plan["lines"]:
        out.append((f"line item amount ({ln['desc']})", ln["amount"]))
    if plan["subtotal_surface"]:
        out.append(("subtotal before discount", plan["subtotal_surface"]))
        out.append(("discount amount", plan["discount_surface"]))
    if "net" not in miss:
        out.append(("net amount excluding VAT", plan["net_surface"]))
    if "vat" not in miss:
        out.append(("VAT amount", plan["vat_surface"]))
    out.append(("total including VAT", plan["total_surface"]))
    if plan["info"]:
        out.append(("converted total, for information only", plan["info"]["currency"]))
        out.append(("converted total amount, for information only", plan["info"]["amount"]))
    return out


def amount_surfaces(plan) -> set[str]:
    s = {plan["net_surface"], plan["vat_surface"], plan["total_surface"]}
    s |= {ln["amount"] for ln in plan["lines"]}
    for k in ("subtotal_surface", "discount_surface"):
        if plan[k]:
            s.add(plan[k])
    if plan["info"]:
        s.add(plan["info"]["amount"])
    miss = set(plan["missing"])
    if "net" in miss:
        s.discard(plan["net_surface"])
    if "vat" in miss:
        s.discard(plan["vat_surface"])
    s.add(plan["total_surface"])
    return s


def date_surfaces(plan) -> list[str]:
    miss = set(plan["missing"])
    out = []
    if "issue_date" not in miss:
        out.append(plan["issue_surface"])
    if "due_date" not in miss:
        out.append(plan["due_surface"])
    if plan["delivery_surface"]:
        out.append(plan["delivery_surface"])
    return out


MISSING_TEXT = {
    "due_date": "a due date (no due date, no payment deadline and no payment terms at all)",
    "invoice_number": "an invoice number (no invoice number and no other reference number of any kind)",
    "issue_date": "an invoice date (the only date on the invoice is the due date)",
    "net": "a net amount (no amount excluding VAT and no line items; only the total is shown)",
    "vat": "a VAT amount (no VAT amount and no VAT rate)",
}


def generator_prompt(plan):
    lang = LANG_NAME[plan["lang"]]
    st = plan["style"]
    must = "\n".join(f"   - {role}: \"{s}\"" for role, s in verbatim_strings(plan))
    rules_missing = ""
    if plan["missing"]:
        rules_missing = ("\n4. The draft deliberately has no " + "; and no ".join(MISSING_TEXT[m] for m in plan["missing"])
                         + ". Do not add one, do not hint at it and do not leave an empty label for it.")
    style = (f"Headings in {'UPPER CASE' if st['caps_headings'] else 'normal case'}; "
             f"{'compact, few blank lines' if st['density'] == 'compact' else 'airy, with blank lines between sections'}; "
             f"you may add a {st['extras'][0]} and a {st['extras'][1]}.")
    return f"""Rewrite the DRAFT invoice below as {TEMPLATE_STYLE[plan['template']]}.

All labels and prose must be in {lang}. You may rephrase labels with natural {lang} synonyms as long as the meaning stays the same. {style}

Hard rules:
1. Copy each of these strings exactly, character for character (same digits, separators, spaces and capitalisation), each at least once:
{must}
2. Keep every value attached to a label with the same meaning as in the draft: the vendor stays the issuer, the customer stays the customer, the net amount stays the amount excluding VAT, a subtotal stays a subtotal before the discount, the delivery date stays a delivery date, the order number stays the customer's order number, the converted amount stays clearly "for information only".
3. Do not add anything else that looks like money, a date or a reference: no other amounts, prices, quantities with prices, percentages other than the ones in the draft, dates, months, years, payment terms in days, invoice/order/customer/OCR/reference numbers, account numbers, currencies or company names. A street address, postal code, phone number and e-mail address are fine.{rules_missing}
{5 if plan["missing"] else 4}. Plain text only: no Markdown, no bold, no code fences, no commentary before or after. Output only the invoice text.

DRAFT:
<<<
{render_draft(plan)}
>>>"""


# --------------------------------------------------------------------------- make_input (noise for shift)

_TYPOS = [("rn", "m"), ("m", "rn"), ("l", "I"), ("I", "l"), ("e", "c"), ("a", "o"), ("h", "b"), ("t", "f"),
          ("ä", "a"), ("ö", "o"), ("ü", "u"), ("å", "a"), ("i", "í"), ("c", "e"), ("n", "ri")]


def _protected_spans(text: str, plan) -> list[tuple[int, int]]:
    spans = []
    strs = [s for _, s in verbatim_strings(plan)] + [plan["vendor_name"], plan["buyer_name"]]
    for s in strs:
        if not s:
            continue
        for m in re.finditer(re.escape(s), text):
            spans.append((m.start(), m.end()))
    # keep the label words next to amounts and dates readable enough: protect digits and currency symbols too
    for m in re.finditer(r"[\d€£$]+", text):
        spans.append((m.start(), m.end()))
    return spans


def add_noise(text: str, plan, seed: int) -> str:
    """Scanned-style noise: OCR letter confusions in words and broken lines, never inside a planned string."""
    rng = random.Random(seed)
    spans = _protected_spans(text, plan)

    def free(a, b):
        return all(b <= s or a >= e for s, e in spans)

    out, pos = [], 0
    for m in re.finditer(r"[^\W\d_]{3,}|[ ]+", text):
        a, b = m.start(), m.end()
        out.append(text[pos:a])
        tok = text[a:b]
        if not free(a, b):
            out.append(tok)
        elif tok.startswith(" "):
            r = rng.random()
            out.append("\n" if r < 0.05 else ("  " if r < 0.10 else tok))
        elif rng.random() < 0.10:
            opts = [(x, y) for x, y in _TYPOS if x in tok]
            if opts:
                x, y = rng.choice(opts)
                i = rng.choice([k for k in range(len(tok)) if tok.startswith(x, k)])
                tok = tok[:i] + y + tok[i + len(x):]
            out.append(tok)
        else:
            out.append(tok)
        pos = b
    out.append(text[pos:])
    noisy = "".join(out)
    lines = noisy.split("\n")
    for i in range(len(lines)):
        if lines[i].strip() and rng.random() < 0.06:
            lines[i] = lines[i] + rng.choice([" |", " .", " ~", " :"])
    return "\n".join(lines)


def make_input(plan, text):
    t = (text or "").replace(" ", " ").replace(" ", " ").replace("\r\n", "\n")
    t = re.sub(r"^```[a-zA-Z]*\n|\n?```\s*$", "", t.strip())
    t = t.strip()
    if plan.get("noise_seed") is not None:
        t = add_noise(t, plan, plan["noise_seed"])
    return t


# --------------------------------------------------------------------------- verify

AMOUNT_RE = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:[ .,]\d{3})+|\d+)[.,]\d{2}(?![.,]?\d)(?!\s?%)")
NUM_DATE_RE = re.compile(r"(?<![\d.])\d{1,4}[./-]\d{1,2}[./-]\d{2,4}(?!\d)")
_MON_ALT = "|".join(sorted({*EN_MONTHS, *EN_MON, "Sept", *SV_MONTHS, *DE_MONTHS, "Maerz"}, key=len, reverse=True))
TEXT_DATE_RES = [
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\.?[ -](?:{_MON_ALT})\.?,?[ -]\d{{2,4}}\b", re.I),
    re.compile(rf"\b(?:{_MON_ALT})\.?\s\d{{1,2}}(?:st|nd|rd|th)?,?\s\d{{4}}\b", re.I),
    re.compile(rf"\b(?:{_MON_ALT})\s\d{{4}}\b", re.I),
]
CUR_RE = re.compile(r"\b(EUR|SEK|USD|GBP|CHF|NOK|DKK|JPY|PLN|CAD|AUD)\b|[€£$]|\bkr\b")
TERMS_RE = re.compile(r"\b\d+\s*(?:days?|dagar|dgr|Tage[n]?|Tg\.)\b", re.I)
MISSING_LABEL_RE = {
    "due_date": re.compile(r"due date|due on|due by|pay(?:able)? by|payment due|förfall|sista betalningsdag|"
                           r"fällig|zahlbar bis|zahlungsziel", re.I),
    "invoice_number": re.compile(r"invoice (?:no|number|#|nr)|fakturan(?:r|ummer)|rechnungs-?n(?:r|ummer)|re-nr", re.I),
    "issue_date": re.compile(r"invoice date|date of issue|issue date|issued on|fakturadatum|rechnungsdatum", re.I),
    "net": re.compile(r"net amount|net total|total net|\bnetto\b|excl\.? vat|excluding vat|exkl\.? moms|ohne mwst|zzgl", re.I),
}


@lru_cache(maxsize=1)
def _company_re():
    names = sorted({c["name"] for c in entities.companies(None)} - _CITY_NAMES, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")


def verify(plan, text):
    t = text
    if not t.strip():
        return False, "empty"
    for role, s in verbatim_strings(plan):
        if s not in t:
            return False, f"missing {role}: {s!r}"
    if "```" in t or "**" in t:
        return False, "markdown"
    amounts = amount_surfaces(plan)
    for m in AMOUNT_RE.finditer(t):
        if m.group(0) not in amounts:
            return False, f"unplanned amount {m.group(0)!r}"
    dates = date_surfaces(plan)
    for m in NUM_DATE_RE.finditer(t):
        if not any(m.group(0) in d for d in dates):
            return False, f"unplanned date {m.group(0)!r}"
    for rx in TEXT_DATE_RES:
        for m in rx.finditer(t):
            if not any(m.group(0).lower() in d.lower() for d in dates):
                return False, f"unplanned date {m.group(0)!r}"
    allowed = {plan["currency"], plan["currency_surface"]}
    if plan["currency"] in SYMBOL_OF:
        allowed.add(SYMBOL_OF[plan["currency"]])
    if plan["info"]:
        allowed.add(plan["info"]["currency"])
    for m in CUR_RE.finditer(t):
        if m.group(0) not in allowed:
            return False, f"unplanned currency {m.group(0)!r}"
    if TERMS_RE.search(t):
        return False, f"payment terms in days: {TERMS_RE.search(t).group(0)!r}"
    for f in plan["missing"]:
        rx = MISSING_LABEL_RE.get(f)
        if rx and rx.search(t):
            return False, f"label for missing {f}: {rx.search(t).group(0)!r}"
    own = (plan["vendor"] + " " + plan["buyer"])
    for m in _company_re().finditer(t):
        if m.group(0) not in own:
            return False, f"unplanned company {m.group(0)!r}"
    return True, ""


def verifier_brief(plan):
    exp = label(plan)
    lines = [
        "The text is one invoice. The correct extraction is:",
        f"- vendor (the issuer/seller): {plan['vendor']}. The customer {plan['buyer']} is NOT the vendor.",
    ]
    surf = {"invoice_number": plan["invoice_number"], "issue_date": plan["issue_surface"],
            "due_date": plan["due_surface"], "net": plan["net_surface"], "vat": plan["vat_surface"],
            "total": plan["total_surface"]}
    for f in ("invoice_number", "issue_date", "due_date", "net", "vat", "total"):
        if exp[f] is None:
            lines.append(f"- {f}: NOT STATED anywhere (expected null). Text that states or lets a reader work out "
                         f"this field would change the answer.")
        else:
            lines.append(f"- {f}: written as '{surf[f]}' (= {exp[f]})")
    lines.append(f"- currency: {plan['currency']} (written as '{plan['currency_surface']}')")
    other = []
    if plan["subtotal_surface"]:
        other.append(f"a subtotal before discount '{plan['subtotal_surface']}' and a discount "
                     f"'{plan['discount_surface']}' (the net is the amount after the discount)")
    if plan["lines"]:
        other.append("line-item amounts " + ", ".join(f"'{l['amount']}'" for l in plan["lines"]))
    if plan["delivery_surface"]:
        other.append(f"a delivery date '{plan['delivery_surface']}' (not the invoice date)")
    if plan["po_ref"]:
        other.append(f"the customer's order number '{plan['po_ref']}' (not the invoice number)")
    if plan["info"]:
        other.append(f"a converted total '{plan['info']['currency']} {plan['info']['amount']}' that is for "
                     f"information only; the invoice is billed in {plan['currency']}")
    if other:
        lines.append("Planned distractors that are fine: " + "; ".join(other) + ".")
    lines.append("Numeric dates are read day-first (European), so e.g. 03/04/2026 is 3 April 2026; that is intended.")
    if plan.get("noise_seed") is not None:
        lines.append("Scanned-style noise (OCR letter typos, broken lines, stray marks) is intentional and fine "
                     "as long as the values above stay readable and attached to the right labels.")
    lines.append("Things that would change the answer: a second issuer company; any unplanned amount, date, "
                 "currency or reference number; a value attached to the wrong label (e.g. the subtotal called the "
                 "net amount, the delivery date called the invoice date, the converted amount presented as payable); "
                 "a field listed as NOT STATED appearing or being derivable (e.g. payment terms for a missing due date).")
    return "\n".join(lines)


# --------------------------------------------------------------------------- schema and settings

def _field_schema():
    return {"type": ["string", "null"]}


def schema(settings):
    props = {f: _field_schema() for f in FIELDS}
    req = list(FIELDS)
    if (settings or {}).get("flag_method") == "confidence_field":
        props["confidence"] = {"type": "object",
                               "properties": {f: {"type": "string", "enum": ["high", "low"]} for f in FIELDS},
                               "required": list(FIELDS), "additionalProperties": False}
        req.append("confidence")
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


def settings_space():
    return {"structured_outputs": [True, False], "verbosity": [None, "low", "medium", "high"],
            "flag_method": ["none", "null_when_unsure", "confidence_field", "two_run_agreement"]}


def port_settings(settings):
    s = dict(settings)
    if s.get("flag_method", "logprob") == "logprob":
        s["flag_method"] = "none"
    s["logprobs"] = False
    return normalise_settings(s)


def normalise_settings(settings):
    """samples = 2 exactly when flag_method is two_run_agreement (the loop calls this after every change)."""
    s = dict(settings)
    if s.get("flag_method") == "two_run_agreement":
        s["samples"] = 2
    else:
        s.pop("samples", None)
    return s


# --------------------------------------------------------------------------- parse

def _walk_top_level(text: str):
    """Yield (key, value, value_start, value_end) for a JSON object's top-level members, or raise ValueError."""
    dec = json.JSONDecoder()
    i = 0
    n = len(text)

    def ws(j):
        while j < n and text[j] in " \t\r\n":
            j += 1
        return j

    i = ws(i)
    if i >= n or text[i] != "{":
        raise ValueError("not an object")
    i = ws(i + 1)
    out = []
    if i < n and text[i] == "}":
        return out, i + 1
    while True:
        if i >= n or text[i] != '"':
            raise ValueError("expected key")
        key, i = dec.raw_decode(text, i)
        i = ws(i)
        if i >= n or text[i] != ":":
            raise ValueError("expected colon")
        i = ws(i + 1)
        vs = i
        val, i = dec.raw_decode(text, i)
        out.append((key, val, vs, i))
        i = ws(i)
        if i < n and text[i] == ",":
            i = ws(i + 1)
            continue
        if i < n and text[i] == "}":
            return out, i + 1
        raise ValueError("expected , or }")


def token_offsets(tokens: list[str], text: str) -> list[tuple[int, int]]:
    """Character span of each token in text. Tokens that are partial UTF-8 bytes (not matching the text) share
    the span up to the next token that matches."""
    offs: list = []
    pos = 0
    pending: list[int] = []
    for t in tokens:
        t = t or ""
        if not pending and t and text.startswith(t, pos):
            offs.append((pos, pos + len(t)))
            pos += len(t)
            continue
        if pending and t:
            j = text.find(t, pos + 1, pos + 1 + len(t) + 6)
            if j != -1:
                for p in pending:
                    offs[p] = (pos, j)
                pending = []
                pos = j
                offs.append((pos, pos + len(t)))
                pos += len(t)
                continue
        pending.append(len(offs))
        offs.append(None)
    for p in pending:
        offs[p] = (pos, len(text))
    return offs


def field_logprobs(text: str, logprobs: list[dict] | None, members) -> dict:
    """Mean token logprob over each field's value characters (inside the quotes, or the bare literal)."""
    out = {f: None for f in FIELDS}
    if not logprobs:
        return out
    toks = [l.get("token") or "" for l in logprobs]
    lps = [l.get("logprob") for l in logprobs]
    offs = token_offsets(toks, text)
    for key, val, vs, ve in members:
        if key not in out:
            continue
        a, b = (vs + 1, ve - 1) if isinstance(val, str) and ve - vs > 2 else (vs, ve)
        sel = [lp for (oa, ob), lp in zip(offs, lps) if lp is not None and oa < b and ob > a]
        if sel:
            out[key] = sum(sel) / len(sel)
    return out


def _parse_one(output) -> dict:
    text = (output or {}).get("text") or ""
    res = {"fields": None, "valid": False, "nonanswer": False, "error": None, "members": [], "confidence": None,
           "text": text}
    s = text.strip()
    if not s or (output or {}).get("refusal"):
        res["nonanswer"] = True
        res["error"] = "empty or refusal"
        return res
    try:
        members, end = _walk_top_level(text)
        if text[end:].strip():
            raise ValueError("trailing text after the object")
    except Exception as e:  # noqa: BLE001
        res["error"] = f"not a bare JSON object: {str(e)[:80]}"
        if s.endswith("?") and "{" not in s:
            res["nonanswer"] = True
        return res
    obj = {k: v for k, v, _, _ in members}
    keys = set(obj)
    extra = keys - set(FIELDS) - {"confidence"}
    missing = set(FIELDS) - keys
    res["members"] = members
    res["confidence"] = obj.get("confidence")
    if missing or extra:
        res["error"] = f"keys: missing {sorted(missing)} extra {sorted(extra)}"
        return res
    bad = [f for f in FIELDS if not (obj[f] is None or isinstance(obj[f], str)
                                     or (isinstance(obj[f], (int, float)) and not isinstance(obj[f], bool)))]
    if bad:
        res["error"] = f"bad value types: {bad}"
        return res
    res["fields"] = {f: obj[f] for f in FIELDS}
    res["valid"] = True
    return res


def parse(output, settings, item):
    try:
        return _parse(output, settings or {}, item)
    except Exception as e:  # noqa: BLE001 - parse must never raise
        return {"fields": None, "valid": False, "nonanswer": False, "error": f"parse crash: {e}", "flags": [],
                "field_logprobs": None, "method": (settings or {}).get("flag_method")}


def _parse(output, settings, item):
    method = settings.get("flag_method") or "none"
    outs = output if isinstance(output, list) else [output]
    first = _parse_one(outs[0])
    valid = first["valid"]
    if valid and first["confidence"] is not None and method != "confidence_field":
        valid = False
        first["error"] = "keys: extra ['confidence']"
    flags: list[str] = []
    flp = None
    if valid:
        fields = first["fields"]
        if method == "logprob":
            flp = field_logprobs(first["text"], outs[0].get("logprobs"), first["members"])
            thr = float(settings.get("flag_threshold", -0.1))
            flags = [f for f in FIELDS if flp[f] is not None and flp[f] < thr]
        elif method == "null_when_unsure":
            flags = [f for f in FIELDS if fields[f] is None]
        elif method == "confidence_field":
            c = first["confidence"]
            if isinstance(c, dict):
                flags = [f for f in FIELDS if str(c.get(f, "")).lower() == "low"]
        elif method == "two_run_agreement":
            second = _parse_one(outs[1]) if len(outs) > 1 else None
            if second is None or not second["valid"]:
                flags = list(FIELDS)
            else:
                flags = [f for f in FIELDS if _norm(f, fields[f]) != _norm(f, second["fields"][f])]
    return {"fields": first["fields"] if valid else None, "valid": valid, "nonanswer": first["nonanswer"],
            "error": first["error"] if not valid else None, "flags": flags, "field_logprobs": flp, "method": method}


# --------------------------------------------------------------------------- score

_AMOUNT_STR = re.compile(r"^-?\d+(\.\d{1,2})?$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm(field, v):
    """Normalised comparison key for a field value; None stays None; unusable values become a sentinel."""
    if v is None:
        return None
    if field in AMOUNT_FIELDS:
        if isinstance(v, bool):
            return ("bad", repr(v))
        if isinstance(v, (int, float)):
            try:
                return q2(Decimal(str(v)))
            except InvalidOperation:
                return ("bad", repr(v))
        if isinstance(v, str) and _AMOUNT_STR.match(v.strip()):
            return q2(Decimal(v.strip()))
        return ("bad", repr(v))
    if not isinstance(v, str):
        return ("bad", repr(v))
    if field == "vendor":
        return re.sub(r"\s+", " ", v.strip()).rstrip(".").casefold()
    if field in DATE_FIELDS:
        return v if _ISO.match(v) else ("bad", v)
    return v.strip().casefold()


def field_correct(field, expected, got) -> bool:
    if expected is None:
        return got is None
    if got is None:
        return False
    return _norm(field, got) == _norm(field, expected)


def _category(field, expected, got) -> str:
    if expected is None:
        return "hallucinated_value"
    if got is None:
        return "missed_value"
    if field in DATE_FIELDS:
        return "wrong_date"
    if field in AMOUNT_FIELDS:
        n = _norm(field, got)
        if isinstance(n, tuple):
            return "amount_format"
        return "wrong_amount"
    return {"vendor": "wrong_vendor", "invoice_number": "wrong_invoice_number", "currency": "wrong_currency"}[field]


def score(expected, parsed):
    base = {"passed": False, "valid": False, "nonanswer": False, "categories": [], "diff": ""}
    if not parsed or not parsed.get("valid"):
        na = bool(parsed and parsed.get("nonanswer"))
        base.update(nonanswer=na, categories=["nonanswer" if na else "format"],
                    diff=f"invalid output: {(parsed or {}).get('error')}",
                    secondary={"fields_correct": 0, "fields_total": 8, "valid_for_flags": 0, "wrong": 0,
                               "flagged": 0, "flag_tp": 0})
        return base
    got = parsed["fields"]
    flags = set(parsed.get("flags") or [])
    wrong, cats, diffs = [], [], []
    for f in FIELDS:
        if not field_correct(f, expected[f], got[f]):
            wrong.append(f)
            cats.append(_category(f, expected[f], got[f]))
            diffs.append(f"{f}: expected {expected[f]!r} got {got[f]!r}")
    tp = len(flags & set(wrong))
    passed = not wrong
    return {"passed": passed, "valid": True, "nonanswer": False, "categories": sorted(set(cats)),
            "diff": "; ".join(diffs) + (f" | flags {sorted(flags)}" if flags else ""),
            "secondary": {"fields_correct": 8 - len(wrong), "fields_total": 8, "valid_for_flags": 1,
                          "wrong": len(wrong), "flagged": len(flags), "flag_tp": tp}}


def aggregate(rows):
    sec = [r.get("secondary") or {} for r in rows]
    fc = sum(s.get("fields_correct", 0) for s in sec)
    ft = sum(s.get("fields_total", 8) for s in sec) or 1
    wrong = sum(s.get("wrong", 0) for s in sec)
    flagged = sum(s.get("flagged", 0) for s in sec)
    tp = sum(s.get("flag_tp", 0) for s in sec)
    nvalid = sum(s.get("valid_for_flags", 0) for s in sec)
    prec = tp / flagged if flagged else None
    rec = tp / wrong if wrong else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else (0.0 if (flagged and wrong) else None)
    return {"field_accuracy": fc / ft, "flag_precision": prec, "flag_recall": rec, "flag_f1": f1,
            "flag_rate": flagged / (8 * nvalid) if nvalid else None, "wrong_fields": wrong, "flagged_fields": flagged,
            "flag_true_positives": tp}


def failure_taxonomy():
    return ["format", "nonanswer", "wrong_vendor", "wrong_invoice_number", "wrong_date", "wrong_currency",
            "wrong_amount", "amount_format", "subtotal_confusion", "hallucinated_value", "missed_value", "other"]


def legacy_markers():
    return [r"\bNEVER\b", r"\bALWAYS\b", r"^IMPORTANT:", r"Do NOT guess", r"Förfallodatum", r"MwSt",
            r"## Glossary", r"expert accounts-payable assistant"]
