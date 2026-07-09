"""Uploaded-data handling for the dashboard's Data page.

Flow: browser upload (base64 CSV) -> source adapter -> shared validation
-> canonical Parquet on disk (data/artifacts/uploaded.parquet). Written to
disk (not kept in memory) so it works across gunicorn workers and, on
Railway, persists on the mounted volume.

`load_snapshot(hour)` then derives everything the map needs from the
canonical data: latest fix per vessel in that hour, density points, and a
grid-based risk aggregation using app.risk (D from transits, C from COG
circular variance — the factors computable from a single uploaded file).
"""
from __future__ import annotations

import base64
import io
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from app.risk import circular_variance, classify, composite_risk
from pipeline.adapters import get_adapter
from pipeline.schema import validate

ARTIFACTS = Path(__file__).resolve().parent.parent / "data" / "artifacts"
UPLOAD_PARQUET = ARTIFACTS / "uploaded.parquet"
UPLOAD_META = ARTIFACTS / "uploaded.meta.json"

MAX_UPLOAD_MB = 50

CLASS_COLOR = {
    "Cargo": "#22D3EE", "Tanker": "#3B82F6", "Passenger": "#A78BFA",
    "Fishing": "#34D399", "Tug": "#FBBF24", "Military": "#F87171",
    "Sailing": "#F472B6", "Pleasure": "#FB923C", "HSC": "#818CF8",
    "Other": "#94A3B8",
}


def save_upload(contents_b64: str, filename: str, source: str,
                mapping_text: str | None) -> dict:
    """Decode an uploaded CSV, run it through the adapter + validation,
    persist canonical parquet, and return a result dict for the UI."""
    header, data = contents_b64.split(",", 1)
    raw_bytes = base64.b64decode(data)
    if len(raw_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        return {"ok": False, "error": f"File exceeds {MAX_UPLOAD_MB} MB demo limit. "
                "For larger datasets use the CLI: python -m pipeline.ingest"}
    if not filename.lower().endswith(".csv"):
        return {"ok": False, "error": "Only .csv files are accepted (not xlsx/zip). "
                "Export or extract to CSV first."}

    mapping_path = None
    if source == "generic":
        if not mapping_text:
            return {"ok": False, "error": "Generic source needs a column-mapping JSON "
                    "(see the instructions panel for the template)."}
        try:
            json.loads(mapping_text)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"Mapping JSON is invalid: {e}"}
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.write(mapping_text)
        tmp.close()
        mapping_path = tmp.name

    try:
        adapter = get_adapter(source, mapping_path)
        canonical = adapter.read(io.BytesIO(raw_bytes))
    except KeyError as e:
        return {"ok": False, "error": f"Missing expected column {e} for source "
                f"'{source}'. Check the format instructions — column names must "
                "match the source's official export exactly."}
    except Exception as e:  # surface parse errors readably
        return {"ok": False, "error": f"Could not parse file as '{source}': {e}"}

    clean, report = validate(canonical)
    if len(clean) == 0:
        return {"ok": False, "error": "All rows were rejected by validation "
                f"(report: {report}). Check coordinates are decimal WGS-84 and "
                "MMSI/timestamp columns are correct.", "report": report}

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(UPLOAD_PARQUET, index=False)
    meta = {"filename": filename, "source": source, "rows": len(clean),
            "vessels": int(clean.mmsi.nunique()),
            "t_min": str(clean.ts.min()), "t_max": str(clean.ts.max())}
    UPLOAD_META.write_text(json.dumps(meta))
    return {"ok": True, "report": report, "meta": meta}


def has_uploaded() -> bool:
    return UPLOAD_PARQUET.exists()


def uploaded_meta() -> dict | None:
    return json.loads(UPLOAD_META.read_text()) if UPLOAD_META.exists() else None


def clear_uploaded() -> None:
    UPLOAD_PARQUET.unlink(missing_ok=True)
    UPLOAD_META.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
def _grid_risk(df: pd.DataFrame, cell_deg: float = 0.02) -> pd.DataFrame:
    """Pseudo-hex aggregation on a lat/lon grid + composite risk (app.risk).

    Uses the factors computable from one uploaded file: D (transits/day)
    and C's course-diversity half. In the full pipeline these come from H3
    cells with all five factors (report §6); the math is identical.
    """
    g = df.copy()
    g["cell_lat"] = (g.lat / cell_deg).round() * cell_deg
    g["cell_lon"] = (g.lon / cell_deg).round() * cell_deg
    days = max((df.ts.max() - df.ts.min()).days, 1)
    agg = (g.groupby(["cell_lat", "cell_lon"])
             .agg(n=("mmsi", "size"),
                  vessels=("mmsi", "nunique"),
                  cog_circ_var=("cog", circular_variance))
             .reset_index())
    agg["transits_per_day"] = agg.vessels / days
    agg = agg[agg.n >= 5]  # ignore near-empty cells
    if len(agg) < 4:
        return pd.DataFrame()
    scored = classify(composite_risk(agg))
    return scored


def load_snapshot(hour: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (fleet, density_points, zones) for the map, from uploaded data."""
    df = pd.read_parquet(UPLOAD_PARQUET)
    win = df[df.ts.dt.hour == hour]
    if len(win) == 0:
        win = df  # fall back to whole file rather than an empty map

    # latest fix per vessel in the window
    fleet = (win.sort_values("ts").groupby("mmsi").tail(1).copy())
    fleet["vessel_type"] = fleet.vessel_class.astype(str)
    fleet["color"] = fleet.vessel_type.map(CLASS_COLOR).fillna("#94A3B8")
    anchored = (fleet.sog.fillna(0) < 0.5) & (fleet.nav_status.isin([1, 5]) |
                                              fleet.nav_status.isna())
    fleet["status"] = np.where(anchored, "Anchored", "Underway")
    fleet["name"] = fleet["name"].fillna("(unnamed)")

    dens = win[["lat", "lon"]].copy()
    dens["w"] = 1.0

    cells = _grid_risk(win)
    zones = []
    if len(cells):
        top = cells[cells.risk_class.isin(["high", "elevated"])] \
                  .nlargest(8, "risk")
        half = 0.01
        for i, (_, c) in enumerate(top.iterrows()):
            zones.append({
                "zone_id": f"U-{i+1:02d}",
                "risk": round(float(c.risk), 2),
                "vessels": int(c.vessels),
                "lat_poly": [c.cell_lat - half, c.cell_lat - half,
                             c.cell_lat + half, c.cell_lat + half, c.cell_lat - half],
                "lon_poly": [c.cell_lon - half, c.cell_lon + half,
                             c.cell_lon + half, c.cell_lon - half, c.cell_lon - half],
                "f_density": round(float(c.D), 2), "f_crossing": round(float(c.C), 2),
                "f_channel": 0.0, "f_weather": 0.0, "f_gaps": 0.0,
            })
    return fleet, dens, pd.DataFrame(zones)
