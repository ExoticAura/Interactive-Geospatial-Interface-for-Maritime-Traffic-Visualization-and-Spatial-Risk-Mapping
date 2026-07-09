import numpy as np
import pandas as pd

from app.risk import circular_variance, classify, composite_risk, norm


def test_norm_bounds():
    s = pd.Series([0, 5, 10, 100])
    n = norm(s)
    assert n.min() >= 0 and n.max() <= 1


def test_circular_variance_parallel_vs_crossing():
    parallel = pd.Series([90, 92, 88, 91])
    crossing = pd.Series([0, 90, 180, 270])
    assert circular_variance(parallel) < 0.05
    assert circular_variance(crossing) > 0.9


def test_composite_and_classify():
    df = pd.DataFrame({
        "transits_per_day": np.random.exponential(5, 200),
        "cog_circ_var": np.random.random(200),
        "encounter_rate": np.random.exponential(0.5, 200),
        "dist_to_coast_m": np.random.uniform(200, 20000, 200),
        "mean_swh": np.random.uniform(0.2, 2.5, 200),
        "mean_wind": np.random.uniform(1, 15, 200),
        "gap_rate": np.random.exponential(0.2, 200),
    })
    scored = classify(composite_risk(df))
    assert scored.risk.between(0, 1).all()
    assert set(scored.risk_class.unique()) <= {"normal", "elevated", "high"}
    assert (scored.risk_class == "high").mean() <= 0.10
