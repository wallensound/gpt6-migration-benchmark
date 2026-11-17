from harness import final as F


def _case(luna_ok, terra_ok, sol=None):
    t = {"gpt-6-luna": {"seed_repeat_pass": luna_ok, "case_migrated": luna_ok, "seed_spread": 0.01, "mean_test": 0.9},
         "gpt-6.1-terra": {"seed_repeat_pass": terra_ok, "case_migrated": terra_ok, "seed_spread": 0.01, "mean_test": 0.9}}
    if sol is not None:
        t["gpt-6.2-sol"] = {"case_migrated": sol, "seed_spread": 0.02, "seed_repeat_pass": True, "mean_test": 0.9}
    return {"status": "evaluated", "targets": t, "opt": {}, "v2": {}}


def test_overall_reproducible(monkeypatch, tmp_path):
    monkeypatch.setattr(F.config, "RUNS", tmp_path)
    cases = {f"0{i}-x": _case(i != 8, True) for i in range(1, 9)}
    for k in ("01-x", "05-x"):
        cases[k]["v2"] = {"r": {"test": 0.89, "target": "gpt-6-luna", "seed": 11}}
    (tmp_path / "P7").mkdir()
    (tmp_path / "P7" / "reproduce.json").write_text('{"pass": true}')
    o = F.overall({"cases": cases})
    assert o["seed_repeat_pass_gpt-6-luna"] == 7 and o["data_version_pass"] and o["verdict"] == "Reproducible"


def test_overall_partly_and_not(monkeypatch, tmp_path):
    monkeypatch.setattr(F.config, "RUNS", tmp_path)
    cases = {f"0{i}-x": _case(i <= 5, True) for i in range(1, 9)}
    for k in ("01-x", "05-x"):
        cases[k]["v2"] = {"r": {"test": 0.89, "target": "gpt-6-luna", "seed": 11}}
    (tmp_path / "P7").mkdir()
    (tmp_path / "P7" / "reproduce.json").write_text('{"pass": true}')
    assert F.overall({"cases": cases})["verdict"] == "Partly reproducible"
    (tmp_path / "P7" / "reproduce.json").write_text('{"pass": false}')
    assert F.overall({"cases": cases})["verdict"] == "Not reproducible"
