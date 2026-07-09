# Maritime Risk Atlas

Interactive geospatial dashboard for maritime traffic visualization and spatial risk mapping (DIPD Final Year Project). Runs in **demo mode** out of the box with synthetic AIS data around the Singapore Strait; swap in real NOAA MarineCadastre pipeline artifacts for production.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.app
# open http://localhost:8050
```

## Deploy to Railway

1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub repo**. The included `Dockerfile` + `railway.toml` are auto-detected.
3. The start command binds gunicorn to Railway's injected `$PORT` (already configured).
4. **Set a hard spending limit** (Workspace → Usage → Set Usage Limits, e.g. $10) — Railway has no default cap.
5. (Later, real data) Attach a volume mounted at `/data` and point the pipeline artifacts there.

Expected cost: Hobby plan, ~$5–15/month. Free fallback: Hugging Face Spaces (Docker SDK).

## Structure

```
app/app.py        Dash app (map, ports layer, search, KPIs, timeline, risk table)
app/mock_data.py  Synthetic fleet / density / risk-zone generator (demo mode)
app/risk.py       Five-factor composite risk index (report §6 reference implementation)
data/ports.csv    Major-ports catalogue (map layer + search index)
pipeline/         Real-data batch stages (01_ingest … 07_zones) — to be added per report §14
tests/            Unit tests
```

## Risk model (summary)

`R = 0.30·D + 0.25·C + 0.15·K + 0.15·W + 0.15·G` per H3 cell —
**D** traffic density · **C** crossing conflicts (course circular variance + encounter rate) ·
**K** channel constraint (coastline distance) · **W** weather exposure (ERA5/Open-Meteo) ·
**G** AIS signal gaps. Full derivations, data sources and validation strategy: see the
project blueprint document, §6.
