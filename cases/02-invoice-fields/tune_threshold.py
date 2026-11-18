"""Tune settings.flag_threshold on train from a stored calibration run (no API calls).

Usage: .venv/Scripts/python cases/02-invoice-fields/tune_threshold.py <prompt_hash>

Reads runs/P3/02-invoice-fields-calibrate-train-<hash>/results.jsonl.gz (each row carries parsed.field_logprobs),
joins the train labels, and picks the threshold that maximises review-flag F1 against the fields that are
actually wrong (ties: the higher threshold-free precision, then the threshold closest to 0). Valid outputs only,
as in the spec.
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import data  # noqa: E402
from harness.cases import Case  # noqa: E402


def main(h: str):
    case = Case("02")
    m = case.mod
    exp = {it["id"]: it["expected"] for it in data.load_split(case.folder, "train")}
    p = ROOT / "runs" / "P3" / f"{case.folder}-calibrate-train-{h}" / "results.jsonl.gz"
    with gzip.open(p, "rt", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    pts = []  # (mean logprob, is_wrong)
    for r in rows:
        pr = r.get("parsed") or {}
        if not pr.get("valid") or not pr.get("field_logprobs"):
            continue
        e = exp[r["item_id"]]
        for fld in m.FIELDS:
            lp = pr["field_logprobs"][fld]
            if lp is None:
                continue
            pts.append((lp, not m.field_correct(fld, e[fld], pr["fields"][fld])))
    wrong = sum(w for _, w in pts)
    print(f"{len(rows)} rows, {len(pts)} field values, {wrong} wrong")
    cands = sorted({lp for lp, _ in pts})
    best = None
    table = []
    for i, lp in enumerate(cands):
        thr = (lp + cands[i + 1]) / 2 if i + 1 < len(cands) else lp + 1e-9  # flag everything <= lp
        flagged = [w for x, w in pts if x < thr]
        tp = sum(flagged)
        prec = tp / len(flagged) if flagged else 0.0
        rec = tp / wrong if wrong else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        table.append((thr, len(flagged), tp, prec, rec, f1))
        key = (f1, prec, thr)
        if best is None or key > best[0]:
            best = (key, thr)
    for t in table[:25]:
        print("thr %.6g flagged %d tp %d prec %.3f rec %.3f f1 %.3f" % t)
    print("wrong-field logprobs:", sorted(round(x, 6) for x, w in pts if w))
    print("best threshold:", best[1] if best else None, "f1", best[0][0] if best else None)


if __name__ == "__main__":
    main(sys.argv[1])
