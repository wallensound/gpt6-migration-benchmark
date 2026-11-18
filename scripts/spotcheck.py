"""Morning-checklist spot-check: 10 dev items of a case (input, expected, model output, score) from calibration runs."""
import glob, json, random, sys
sys.path.insert(0, ".")
from harness.evaluate import read_results
from harness import data
from harness.cases import Case

c = Case(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
d = sorted(glob.glob(f"runs/P3/{c.folder}-calibrate-dev-*"))[-1]
rows = read_results(d); items = {i["id"]: i for i in data.load_split(c.folder, "dev")}
random.Random(5).shuffle(rows)
fails = [r for r in rows if not r["passed"]][:4]
for r in fails + [r for r in rows if r["passed"]][: n - len(fails)]:
    it = items[r["item_id"]]
    print(f"[{r['slice']}] pass={r['passed']} diff={r['diff'][:200]!r}\n  EXP={json.dumps(it['expected'], ensure_ascii=False)[:300]}\n  OUT={r['raw_output'][:300]!r}\n  IN={it['input'][:300]!r}\n")
