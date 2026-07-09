"""Composite risk index — reference implementation of report §6.

Five factors per H3 cell:
  D  traffic density        norm(log1p(distinct-vessel transits per day))
  C  crossing conflicts     0.5*norm(circular variance of COG) + 0.5*norm(encounter rate)
  K  channel constraint     1 - min(2*dist_to_coast / 10km, 1)          [static]
  W  weather exposure       0.6*norm(mean sig. wave height) + 0.4*norm(mean wind)
  G  AIS signal gaps        norm(gap events per vessel-hour)

R = w_D*D + w_C*C + w_K*K + w_W*W + w_G*G   (weights sum to 1, user-adjustable)

This module is pure pandas/numpy so it runs identically on the mock demo
and on real pipeline output (hex-level aggregates from DuckDB).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {"D": 0.30, "C": 0.25, "K": 0.15, "W": 0.15, "G": 0.15}


def norm(s: pd.Series, lo_q: float = 0.01, hi_q: float = 0.99) -> pd.Series:
    """Robust min-max normalization to [0,1] using percentile clamps."""
    lo, hi = s.quantile(lo_q), s.quantile(hi_q)
    if hi <= lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return ((s - lo) / (hi - lo)).clip(0, 1)


def circular_variance(cog_deg: pd.Series) -> float:
    """1 - mean resultant length of course-over-ground angles. 0=parallel, 1=crossing."""
    th = np.deg2rad(cog_deg.dropna().to_numpy())
    if len(th) == 0:
        return 0.0
    r_bar = np.hypot(np.cos(th).mean(), np.sin(th).mean())
    return float(1.0 - r_bar)


def channel_constraint(dist_to_coast_m: pd.Series, w_ref_m: float = 10_000) -> pd.Series:
    """K factor from distance to nearest coastline (per cell centroid)."""
    w_nav = 2.0 * dist_to_coast_m
    return (1.0 - (w_nav / w_ref_m).clip(upper=1.0)).clip(0, 1)


def composite_risk(hex_df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Compute normalized factors + composite score on a hex-aggregate frame.

    Expects columns: transits_per_day, cog_circ_var, encounter_rate,
    dist_to_coast_m, mean_swh, mean_wind, gap_rate. Missing columns are
    treated as zero contribution (factor weight effectively redistributed
    is the caller's choice; here we just score what exists).
    """
    w = dict(DEFAULT_WEIGHTS, **(weights or {}))
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}  # renormalize defensively

    df = hex_df.copy()
    df["D"] = norm(np.log1p(df.get("transits_per_day", pd.Series(0, index=df.index))))
    cv = norm(df.get("cog_circ_var", pd.Series(0, index=df.index)))
    enc = norm(df.get("encounter_rate", pd.Series(0, index=df.index)))
    df["C"] = 0.5 * cv + 0.5 * enc
    if "dist_to_coast_m" in df:
        df["K"] = channel_constraint(df["dist_to_coast_m"])
    else:
        df["K"] = 0.0
    swh = norm(df.get("mean_swh", pd.Series(0, index=df.index)))
    wind = norm(df.get("mean_wind", pd.Series(0, index=df.index)))
    df["W"] = 0.6 * swh + 0.4 * wind
    df["G"] = norm(df.get("gap_rate", pd.Series(0, index=df.index)))

    df["risk"] = sum(w[f] * df[f] for f in ["D", "C", "K", "W", "G"])
    return df


def classify(df: pd.DataFrame, high_pct: float = 0.95, elevated_pct: float = 0.85) -> pd.DataFrame:
    """Quantile classification; percentiles are the user-defined threshold hook."""
    df = df.copy()
    hi = df["risk"].quantile(high_pct)
    el = df["risk"].quantile(elevated_pct)
    df["risk_class"] = np.select(
        [df["risk"] >= hi, df["risk"] >= el], ["high", "elevated"], default="normal"
    )
    return df
