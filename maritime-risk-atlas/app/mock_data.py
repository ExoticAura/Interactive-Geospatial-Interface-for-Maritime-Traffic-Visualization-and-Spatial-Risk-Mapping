"""Synthetic AIS demo data for the Maritime Risk Atlas skeleton.

Generates a plausible fleet around the Singapore Strait so the dashboard
runs with zero external data. Replace with the real pipeline artifacts
(data/artifacts/*.parquet) in production mode.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

VESSEL_TYPES = ["Cargo", "Tanker", "Passenger", "Fishing", "Tug", "Military", "Sailing"]
TYPE_PROB = [0.40, 0.22, 0.08, 0.14, 0.08, 0.03, 0.05]
TYPE_COLOR = {
    "Cargo": "#22D3EE", "Tanker": "#3B82F6", "Passenger": "#A78BFA",
    "Fishing": "#34D399", "Tug": "#FBBF24", "Military": "#F87171", "Sailing": "#F472B6",
}

# Rough west->east waypoints of the Singapore Strait TSS
LANE = [(1.13, 103.50), (1.16, 103.68), (1.20, 103.85), (1.23, 104.02), (1.28, 104.18)]


def _interp_lane(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Piecewise-linear position along the lane for t in [0,1]."""
    pts = np.array(LANE)
    seg = np.minimum((t * (len(pts) - 1)).astype(int), len(pts) - 2)
    frac = t * (len(pts) - 1) - seg
    lat = pts[seg, 0] + (pts[seg + 1, 0] - pts[seg, 0]) * frac
    lon = pts[seg, 1] + (pts[seg + 1, 1] - pts[seg, 1]) * frac
    return lat, lon


def make_fleet(n: int = 400, hour: int = 12) -> pd.DataFrame:
    """One synthetic AIS snapshot: n vessels, positions vary with `hour`."""
    types = RNG.choice(VESSEL_TYPES, size=n, p=TYPE_PROB)
    # 70% follow the strait lane (both directions), 30% scattered near anchorages
    on_lane = RNG.random(n) < 0.70
    t = (RNG.random(n) + hour / 24.0) % 1.0
    lat, lon = _interp_lane(t)
    lat = lat + RNG.normal(0, 0.015, n)
    lon = lon + RNG.normal(0, 0.020, n)
    # anchorage clusters
    anch = ~on_lane
    centers = np.array([[1.22, 103.75], [1.10, 103.92], [1.06, 104.10]])
    pick = RNG.integers(0, len(centers), anch.sum())
    lat[anch] = centers[pick, 0] + RNG.normal(0, 0.02, anch.sum())
    lon[anch] = centers[pick, 1] + RNG.normal(0, 0.03, anch.sum())

    eastbound = RNG.random(n) < 0.5
    cog = np.where(eastbound, RNG.normal(75, 8, n), RNG.normal(255, 8, n)) % 360
    sog = np.clip(RNG.normal(12, 4, n), 0, 24)
    sog[anch] = np.clip(RNG.normal(0.2, 0.3, anch.sum()), 0, 1.5)
    status = np.where(sog < 0.5, "Anchored", "Underway")

    return pd.DataFrame({
        "mmsi": RNG.integers(200_000_000, 799_999_999, n),
        "name": [f"MV DEMO {i:03d}" for i in range(n)],
        "vessel_type": types,
        "lat": lat, "lon": lon, "sog": sog.round(1), "cog": cog.round(0),
        "status": status,
        "color": [TYPE_COLOR[t_] for t_ in types],
    })


def make_density_points(n: int = 6000, hour: int = 12) -> pd.DataFrame:
    """Point cloud for the density heatmap (denser along the lane)."""
    t = RNG.random(n)
    lat, lon = _interp_lane(t)
    spread = 0.010 + 0.02 * np.abs(np.sin(t * np.pi * 3 + hour / 4))
    return pd.DataFrame({
        "lat": lat + RNG.normal(0, spread, n),
        "lon": lon + RNG.normal(0, spread * 1.4, n),
        "w": RNG.exponential(1.0, n),
    })


def make_risk_zones(hour: int = 12) -> pd.DataFrame:
    """Mock high-risk zones with a five-factor breakdown (see report §6.2)."""
    zones = [
        # zone_id, center lat/lon, radius_deg, base risk
        ("Z-18", 1.075, 104.12, 0.075, 0.92),
        ("Z-07", 1.170, 103.70, 0.065, 0.87),
        ("Z-12", 1.320, 104.05, 0.080, 0.76),
        ("Z-03", 1.020, 103.62, 0.060, 0.65),
        ("Z-09", 1.130, 103.95, 0.055, 0.58),
    ]
    rows = []
    for zid, clat, clon, r, base in zones:
        risk = float(np.clip(base + 0.03 * np.sin(hour / 3 + hash(zid) % 7), 0, 1))
        ang = np.linspace(0, 2 * np.pi, 9)
        wobble = 1 + 0.25 * np.sin(ang * 3 + hash(zid) % 5)
        rows.append({
            "zone_id": zid,
            "risk": round(risk, 2),
            "vessels": int(600 + 1400 * risk + 50 * np.sin(hour)),
            "lat_poly": (clat + r * wobble * np.sin(ang)).tolist(),
            "lon_poly": (clon + r * 1.4 * wobble * np.cos(ang)).tolist(),
            # five-factor breakdown, roughly consistent with composite
            "f_density": round(min(1, risk * RNG.uniform(0.9, 1.1)), 2),
            "f_crossing": round(min(1, risk * RNG.uniform(0.7, 1.1)), 2),
            "f_channel": round(RNG.uniform(0.3, 0.9), 2),
            "f_weather": round(RNG.uniform(0.1, 0.5), 2),
            "f_gaps": round(RNG.uniform(0.1, 0.6), 2),
        })
    return pd.DataFrame(rows)


def load_ports(path: str = "data/ports.csv") -> pd.DataFrame:
    return pd.read_csv(path)
