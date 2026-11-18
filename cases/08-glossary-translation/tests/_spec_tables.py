"""Regenerates the glossary/domain tables at the end of spec.md from case.py (run manually before sealing)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.cases import Case  # noqa: E402

MARK = "\n## Glossary (40 terms, in the prompt)\n"


def table(ts):
    rows = ["| Swedish | required English | forbidden alternatives | inflected forms | compounds (English) |",
            "| --- | --- | --- | --- | --- |"]
    for t in ts:
        comps = "; ".join(f"{c} ({e})" for c, e in t["compounds"]) or "-"
        rows.append(f"| {t['sv']} | {t['en']} | {', '.join(t['forbidden'])} | {', '.join(t['forms'])} | {comps} |")
    return "\n".join(rows)


if __name__ == "__main__":
    case = Case("08")
    m = case.mod
    p = case.dir / "spec.md"
    head = p.read_text(encoding="utf-8").split(MARK)[0]
    doms = "\n".join(f"- {k}: {', '.join(v['terms'])}. Product types: {', '.join(v['products'])}."
                     for k, v in {**m.DOMAINS, **m.SHIFT_DOMAINS}.items())
    out = (head + MARK + "\n" + table(m.GLOSSARY)
           + "\n\n## Extension glossary (20 terms, shift only, supplied with the item)\n\n" + table(m.EXTENSION)
           + f"\n\n## Domains\n\nGeneric main terms (usable in every main domain): {', '.join(m.GENERIC)}.\n\n"
           + doms + "\n")
    p.write_text(out, encoding="utf-8", newline="\n")
