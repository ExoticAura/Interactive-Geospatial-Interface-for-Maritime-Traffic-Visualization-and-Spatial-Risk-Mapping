"""Stage 01+02: ingest any AIS source -> validated canonical Parquet.

Usage:
  python -m pipeline.ingest --source noaa    data/raw/AIS_2024_07_01.csv
  python -m pipeline.ingest --source dma     data/raw/aisdk-2024-07-01.csv
  python -m pipeline.ingest --source generic data/raw/kaggle.csv \
         --mapping pipeline/mappings/example_mapping.json
  # optional: --bbox min_lon,min_lat,max_lon,max_lat  --out path.parquet

Output: data/artifacts/ais_points.parquet (canonical schema) plus a
data-quality report (rows dropped per rule) printed and saved as JSON.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.adapters import get_adapter
from pipeline.schema import validate


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("files", nargs="+", help="one or more source CSV files")
    p.add_argument("--source", required=True, help="noaa | dma | generic")
    p.add_argument("--mapping", help="JSON mapping file (generic source)")
    p.add_argument("--bbox", help="min_lon,min_lat,max_lon,max_lat study-area clip")
    p.add_argument("--out", default="data/artifacts/ais_points.parquet")
    args = p.parse_args()

    adapter = get_adapter(args.source, args.mapping)
    frames, reports = [], []
    for f in args.files:
        df = adapter.read(f)
        df, rep = validate(df)
        rep["file"] = str(f)
        frames.append(df)
        reports.append(rep)
        print(f"[ingest] {f}: {rep['rows_in']:,} -> {rep['rows_out']:,} rows")

    import pandas as pd
    out = pd.concat(frames, ignore_index=True)

    if args.bbox:
        x0, y0, x1, y1 = map(float, args.bbox.split(","))
        before = len(out)
        out = out[out.lon.between(x0, x1) & out.lat.between(y0, y1)]
        print(f"[ingest] bbox clip: {before:,} -> {len(out):,} rows")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    Path(str(out_path) + ".quality.json").write_text(json.dumps(reports, indent=2))
    print(f"[ingest] wrote {len(out):,} canonical rows -> {out_path}")


if __name__ == "__main__":
    main()
