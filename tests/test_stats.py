import numpy as np
import pytest

from harness import stats as S


def test_wilson_known_value():
    lo, hi = S.wilson(270, 300)
    assert lo == pytest.approx(0.8609, abs=2e-3) and hi == pytest.approx(0.9290, abs=2e-3)
    assert S.wilson(0, 10)[0] == 0.0


def test_mcnemar():
    cand = np.array([1] * 20 + [0] * 2 + [1] * 50, bool)
    cur = np.array([0] * 20 + [1] * 2 + [1] * 50, bool)
    r = S.mcnemar_exact(cand, cur)
    assert r["b"] == 20 and r["c"] == 2 and r["p_value"] < 0.001
    assert S.mcnemar_exact(cur, cur)["p_value"] == 1.0


def test_holm():
    assert S.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_noninferiority():
    a = np.random.default_rng(1).random(300) < 0.90
    same = S.noninferiority(a, a)
    assert same["noninferior"] and same["diff"] == 0
    worse = S.noninferiority(np.zeros(300, bool), np.ones(300, bool))
    assert not worse["noninferior"] and worse["p_value"] > 0.5


def test_bootstrap_is_seeded():
    a = np.array([1, 0, 1, 1, 0] * 20)
    b = np.array([1, 1, 0, 1, 0] * 20)
    assert np.array_equal(S.paired_bootstrap(a, b, 100, 3), S.paired_bootstrap(a, b, 100, 3))


def test_flip_rate():
    assert S.flip_rate([[1, 1, 0, 0], [1, 0, 0, 1], [1, 1, 0, 0]]) == pytest.approx(0.5)
