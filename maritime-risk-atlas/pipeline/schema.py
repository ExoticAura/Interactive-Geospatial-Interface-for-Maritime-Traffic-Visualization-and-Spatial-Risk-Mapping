"""Canonical AIS schema — the single data contract for the whole platform.

Every data source (NOAA MarineCadastre, Danish DMA, Kaggle extracts, a future
live feed) is converted BY AN ADAPTER into this schema. Everything downstream
(trajectories, density, risk scoring, the dashboard) reads ONLY this schema,
which is what makes the platform data-source agnostic.

Required fields:  mmsi, ts, lat, lon
Optional fields:  sog, cog, heading, nav_status, vessel_class,
                  name, imo, callsign, length, width, draft
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---- canonical dtypes -------------------------------------------------------
CANONICAL_COLUMNS: dict[str, str] = {
    "mmsi": "int64",            # 9-digit vessel identity
    "ts": "datetime64[ns, UTC]",  # UTC timestamp of fix
    "lat": "float64",           # WGS-84 degrees
    "lon": "float64",
    "sog": "float32",           # knots; NaN = unavailable
    "cog": "float32",           # degrees [0,360); NaN = unavailable
    "heading": "float32",       # true heading degrees; NaN = unavailable
    "nav_status": "Int8",       # AIS nav status code 0-15; <NA> = unknown
    "vessel_class": "category", # canonical class, see VESSEL_CLASSES
    "name": "string",
    "imo": "string",
    "callsign": "string",
    "length": "float32",        # metres
    "width": "float32",
    "draft": "float32",
}

REQUIRED = ["mmsi", "ts", "lat", "lon"]

VESSEL_CLASSES = [
    "Cargo", "Tanker", "Passenger", "Fishing", "Tug",
    "Military", "Sailing", "Pleasure", "HSC", "Other",
]

# AIS numeric ship-type code -> canonical class (ITU-R M.1371 ranges)
def class_from_ais_code(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "Other"
    if 70 <= c <= 79:
        return "Cargo"
    if 80 <= c <= 89:
        return "Tanker"
    if 60 <= c <= 69:
        return "Passenger"
    if c == 30:
        return "Fishing"
    if c in (31, 32, 52):
        return "Tug"
    if c in (35, 55):
        return "Military"
    if c == 36:
        return "Sailing"
    if c == 37:
        return "Pleasure"
    if 40 <= c <= 49:
        return "HSC"
    return "Other"


# ---- shared validation (source-independent; report §14 stage 02) ------------
INVALID_MMSI = {0, 1, 111111111, 123456789, 999999999}


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the cleaning rules from report §14 stage 02.

    Returns (clean_df, drop_report) where drop_report counts rows removed
    per rule — persist this as the data-quality report for the thesis.
    """
    report: dict[str, int] = {}
    n0 = len(df)

    # required fields present
    df = df.dropna(subset=[c for c in REQUIRED if c in df.columns])
    report["missing_required"] = n0 - len(df)

    # coordinate bounds (also kills 91/181 sentinels)
    m = df.lat.between(-90, 90) & df.lon.between(-180, 180)
    report["bad_coords"] = int((~m).sum())
    df = df[m]

    # sentinel / impossible dynamics -> NaN (not row drops)
    if "sog" in df:
        df.loc[df.sog >= 102.0, "sog"] = np.nan       # 102.3 = unavailable
        bad = df.sog > 40
        report["sog_gt_40kn"] = int(bad.sum())
        df = df[~bad.fillna(False)]
    if "cog" in df:
        df.loc[df.cog >= 360.0, "cog"] = np.nan       # 360 = unavailable
    if "heading" in df:
        df.loc[df.heading >= 511.0, "heading"] = np.nan  # 511 = unavailable

    # MMSI validity: 9 digits, not a known test value
    m = df.mmsi.between(100_000_000, 999_999_999) & ~df.mmsi.isin(INVALID_MMSI)
    report["bad_mmsi"] = int((~m).sum())
    df = df[m]

    # dedupe on (mmsi, ts)
    before = len(df)
    df = df.drop_duplicates(subset=["mmsi", "ts"])
    report["duplicates"] = before - len(df)

    report["rows_in"] = n0
    report["rows_out"] = len(df)
    return df.reset_index(drop=True), report


def coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Force canonical dtypes; add missing optional columns as nulls."""
    for col, dtype in CANONICAL_COLUMNS.items():
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df))
        if col == "ts":
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
        elif col == "vessel_class":
            df[col] = pd.Categorical(
                df[col].fillna("Other"), categories=VESSEL_CLASSES)
        else:
            df[col] = df[col].astype(dtype, errors="ignore")
    return df[list(CANONICAL_COLUMNS)]
