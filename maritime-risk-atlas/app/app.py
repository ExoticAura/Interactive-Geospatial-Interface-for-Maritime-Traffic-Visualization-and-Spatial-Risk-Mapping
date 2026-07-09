"""Maritime Risk Atlas — Dash skeleton (demo mode + user data upload).

Run locally:   python -m app.app          -> http://localhost:8050
Production:    gunicorn app.app:server --bind 0.0.0.0:$PORT --workers 2 --preload
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update

from app import data_store
from app.mock_data import load_ports, make_density_points, make_fleet, make_risk_zones

# ---------- theme tokens ----------
BG = "#0B1220"
SURFACE = "#111A2E"
CYAN = "#22D3EE"
BLUE = "#3B82F6"
TEXT = "#E5E7EB"
TEXT2 = "#94A3B8"
AMBER = "#F59E0B"
RED = "#EF4444"
GREEN = "#10B981"

PORTS = load_ports(os.path.join(os.path.dirname(__file__), "..", "data", "ports.csv"))

app = Dash(__name__, title="Maritime Risk Atlas")
server = app.server  # gunicorn entrypoint


# ---------- figure builder ----------
def build_map(fleet: pd.DataFrame, dens: pd.DataFrame, zones: pd.DataFrame,
              center=None, zoom=None) -> go.Figure:
    fig = go.Figure()

    if len(dens):
        fig.add_trace(go.Densitymapbox(
            lat=dens.lat, lon=dens.lon, z=dens.w, radius=18,
            colorscale=[[0, "rgba(30,64,175,0)"], [0.4, "rgba(13,148,136,0.55)"],
                        [0.75, "rgba(251,191,36,0.75)"], [1, "rgba(249,115,22,0.9)"]],
            showscale=False, hoverinfo="skip", name="Density",
        ))

    for _, z in zones.iterrows():
        color = RED if z.risk >= 0.8 else AMBER
        fig.add_trace(go.Scattermapbox(
            lat=z.lat_poly, lon=z.lon_poly, mode="lines", fill="toself",
            fillcolor=("rgba(239,68,68,0.18)" if color == RED else "rgba(245,158,11,0.15)"),
            line=dict(color=color, width=2),
            name=z.zone_id, hovertext=f"{z.zone_id} · risk {z.risk} · {z.vessels} vessels",
            hoverinfo="text",
        ))

    for status, col_override in [("Underway", None), ("Anchored", "#F87171")]:
        sub = fleet[fleet.status == status]
        if not len(sub):
            continue
        fig.add_trace(go.Scattermapbox(
            lat=sub.lat, lon=sub.lon, mode="markers",
            marker=dict(size=9, color=col_override or sub.color),
            customdata=sub[["name", "mmsi", "vessel_type", "sog", "cog", "status"]],
            hovertemplate="<b>%{customdata[0]}</b> (%{customdata[5]})<br>"
                          "MMSI %{customdata[1]}<br>%{customdata[2]} · "
                          "%{customdata[3]} kn · COG %{customdata[4]}°<extra></extra>",
            name=f"Vessels ({status})",
        ))

    fig.add_trace(go.Scattermapbox(
        lat=PORTS.lat, lon=PORTS.lon, mode="markers+text",
        marker=dict(size=10, color=BLUE),
        text=PORTS.name, textposition="top right",
        textfont=dict(color=TEXT2, size=10),
        hovertemplate="<b>%{text}</b><extra>Port</extra>", name="Ports",
    ))

    fig.update_layout(
        mapbox=dict(style="carto-darkmatter",
                    center=center or {"lat": 1.20, "lon": 103.90},
                    zoom=zoom if zoom is not None else 9),
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BG, showlegend=False, uirevision="keep",
    )
    return fig


def kpi_card(label: str, value: str, sub: str) -> html.Div:
    return html.Div([
        html.Div(label, style={"fontSize": 11, "color": TEXT2, "textTransform": "uppercase",
                               "letterSpacing": "0.5px"}),
        html.Div(value, style={"fontSize": 26, "fontWeight": 600, "color": CYAN,
                               "fontFamily": "monospace"}),
        html.Div(sub, style={"fontSize": 11, "color": TEXT2}),
    ], style={"background": SURFACE, "borderRadius": 8, "padding": "10px 16px",
              "boxShadow": "0 4px 12px rgba(0,0,0,0.3)", "minWidth": 150})


def search_options():
    opts = [{"label": f"⚓ {r['name']} ({r.country})",
             "value": f"port|{r.lat}|{r.lon}"} for _, r in PORTS.iterrows()]
    countries = PORTS.groupby("country")[["lat", "lon"]].mean().reset_index()
    opts += [{"label": f"🌐 {r.country}", "value": f"country|{r.lat}|{r.lon}"}
             for _, r in countries.iterrows()]
    return opts


# ---------- Data page: format instructions ----------
MAPPING_TEMPLATE = (
    '{\n  "columns": {"mmsi": "MMSI", "ts": "time", "lat": "latitude",\n'
    '              "lon": "longitude", "sog": "speed", "cog": "course",\n'
    '              "heading": "hdg", "name": "shipname", "vessel_class": "shiptype"},\n'
    '  "ts_format": null,  "ts_unit": null,\n'
    '  "sog_unit": "knots",\n'
    '  "vessel_class_is_ais_code": true\n}'
)


def instructions_panel() -> html.Details:
    li = lambda *kids: html.Li(kids, style={"marginBottom": 4})
    code = lambda s: html.Code(s, style={"color": CYAN})
    return html.Details([
        html.Summary("📄 Accepted formats & how to arrange your file (click to expand)",
                     style={"cursor": "pointer", "color": CYAN, "fontSize": 13}),
        html.Div(style={"fontSize": 12.5, "color": TEXT, "lineHeight": 1.6,
                        "padding": "10px 4px"}, children=[
            html.P(["Upload a ", html.B(".csv"), f" file (max {data_store.MAX_UPLOAD_MB} MB "
                    "via the browser — use the CLI for bigger files) and pick the format "
                    "that matches it:"]),
            html.Ul([
                li(html.B("NOAA MarineCadastre"), " — the daily CSV exactly as downloaded ",
                   "(", code("MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselType, "
                             "Status, …"), "). Don't rename columns."),
                li(html.B("Danish DMA (aisdk)"), " — as downloaded from web.ais.dk ",
                   "(", code("# Timestamp, MMSI, Latitude, Longitude, SOG, COG, Ship type, …"),
                   ", timestamps dd/mm/yyyy HH:MM:SS)."),
                li(html.B("Generic / any CSV"), " — must contain at minimum a vessel ID, "
                   "timestamp, latitude and longitude column (any names). Paste a mapping "
                   "JSON telling the app which column is which — template below."),
            ]),
            html.P(html.B("Requirements (all formats):")),
            html.Ul([
                li("Coordinates in decimal WGS-84 degrees (e.g. 1.2644, 103.84) — ",
                   html.B("not"), " degrees-minutes-seconds."),
                li("Timestamps in UTC (or set ", code("ts_format"), " / ",
                   code("ts_unit"), " in the mapping for other formats/epoch seconds)."),
                li("Speed in knots by default; m/s or km/h supported via ",
                   code("sog_unit"), " in the mapping."),
                li("One row = one position fix. Extra columns are ignored."),
            ]),
            html.P(html.B("Cleaned automatically (no need to pre-clean):")),
            html.Ul([
                li("AIS sentinel values: SOG 102.3, COG 360, heading 511, lat/lon 91/181 → treated as missing."),
                li("Invalid MMSIs (0, 111111111, non-9-digit), out-of-range coordinates, exact duplicates → dropped."),
                li("You'll get a per-rule quality report after upload."),
            ]),
            html.P(html.B("Not accepted:"), style={"marginBottom": 2}),
            html.Ul([li(".xlsx / .zip / GeoPackage (convert to CSV first)"),
                     li("Files without a timestamp or without coordinates")]),
            html.P("Mapping JSON template (Generic format):"),
            html.Pre(MAPPING_TEMPLATE, style={"background": BG, "padding": 10,
                                              "borderRadius": 6, "fontSize": 11.5,
                                              "color": TEXT2, "overflowX": "auto"}),
        ]),
    ], style={"background": SURFACE, "borderRadius": 8, "padding": "10px 14px",
              "margin": "4px 0 10px"})


# ---------- layout ----------
app.layout = html.Div(style={"background": BG, "minHeight": "100vh", "color": TEXT,
                             "fontFamily": "Inter, system-ui, sans-serif"}, children=[
    html.Div(style={"display": "flex", "gap": 16, "alignItems": "center",
                    "padding": "12px 24px", "flexWrap": "wrap"}, children=[
        html.Div([html.Span("Maritime Risk ", style={"fontWeight": 700, "fontSize": 20}),
                  html.Span("Atlas", style={"fontWeight": 700, "fontSize": 20, "color": CYAN})]),
        html.Div(id="kpis", style={"display": "flex", "gap": 12, "flexWrap": "wrap"}),
    ]),

    # ---- DATA SOURCE section ----
    html.Div(style={"padding": "0 24px 8px"}, children=[
        html.Div("DATA SOURCE", style={"fontSize": 11, "color": CYAN,
                                       "letterSpacing": "1px", "marginBottom": 6}),
        instructions_panel(),
        html.Div(style={"display": "flex", "gap": 12, "flexWrap": "wrap",
                        "alignItems": "flex-start"}, children=[
            dcc.RadioItems(id="data-mode",
                           options=[{"label": " Demo data (synthetic)", "value": "demo"},
                                    {"label": " Uploaded data", "value": "uploaded",
                                     "disabled": not data_store.has_uploaded()}],
                           value="demo", inline=True,
                           style={"color": TEXT, "fontSize": 13}),
            dcc.Dropdown(id="upload-source", value="noaa", clearable=False,
                         options=[{"label": "NOAA MarineCadastre CSV", "value": "noaa"},
                                  {"label": "Danish DMA (aisdk) CSV", "value": "dma"},
                                  {"label": "Generic CSV + mapping JSON", "value": "generic"}],
                         style={"width": 260, "color": "#111"}),
            dcc.Upload(id="upload-data",
                       children=html.Div(["⬆ Drop CSV here or ",
                                          html.Span("browse", style={"color": CYAN})]),
                       style={"width": 280, "height": 38, "lineHeight": "38px",
                              "border": f"1px dashed {TEXT2}", "borderRadius": 8,
                              "textAlign": "center", "fontSize": 13, "cursor": "pointer"},
                       max_size=data_store.MAX_UPLOAD_MB * 1024 * 1024, multiple=False),
        ]),
        html.Div(dcc.Textarea(id="mapping-json", placeholder="Mapping JSON (Generic format only)…",
                              style={"width": "100%", "maxWidth": 560, "height": 90,
                                     "background": SURFACE, "color": TEXT,
                                     "border": f"1px solid {TEXT2}", "borderRadius": 6,
                                     "fontFamily": "monospace", "fontSize": 12,
                                     "display": "none", "marginTop": 8}),
                 id="mapping-wrap"),
        dcc.Loading(html.Div(id="upload-status", style={"marginTop": 8, "fontSize": 13})),
    ]),

    # ---- controls ----
    html.Div(style={"display": "flex", "gap": 16, "padding": "4px 24px 12px",
                    "alignItems": "center", "flexWrap": "wrap"}, children=[
        dcc.Dropdown(id="search", options=search_options(), placeholder="Search port or country…",
                     style={"width": 320, "color": "#111"}),
        dcc.Dropdown(id="type-filter", multi=True, placeholder="Vessel types (all)",
                     options=[{"label": t, "value": t} for t in
                              ["Cargo", "Tanker", "Passenger", "Fishing", "Tug",
                               "Military", "Sailing", "Pleasure", "HSC", "Other"]],
                     style={"width": 380, "color": "#111"}),
    ]),

    dcc.Graph(id="map", style={"height": "58vh", "padding": "0 24px"},
              config={"displayModeBar": False}),

    html.Div(style={"padding": "12px 40px"}, children=[
        html.Div("TIMELINE (hour of day, UTC)", style={"fontSize": 11, "color": CYAN,
                                                       "letterSpacing": "1px",
                                                       "marginBottom": 6}),
        dcc.Slider(id="hour", min=0, max=23, step=1, value=12,
                   marks={h: {"label": f"{h:02d}:00", "style": {"color": TEXT2}}
                          for h in range(0, 24, 3)}),
    ]),

    html.Div(id="risk-table", style={"padding": "0 24px 32px"}),
])


# ---------- callbacks ----------
@app.callback(Output("mapping-wrap", "children"), Input("upload-source", "value"),
              State("mapping-json", "value"), prevent_initial_call=False)
def toggle_mapping(source, current):
    style = {"width": "100%", "maxWidth": 560, "height": 90, "background": SURFACE,
             "color": TEXT, "border": f"1px solid {TEXT2}", "borderRadius": 6,
             "fontFamily": "monospace", "fontSize": 12, "marginTop": 8,
             "display": "block" if source == "generic" else "none"}
    return dcc.Textarea(id="mapping-json", value=current or MAPPING_TEMPLATE
                        if source == "generic" else current,
                        placeholder="Mapping JSON…", style=style)


@app.callback(
    Output("upload-status", "children"), Output("data-mode", "options"),
    Output("data-mode", "value"),
    Input("upload-data", "contents"),
    State("upload-data", "filename"), State("upload-source", "value"),
    State("mapping-json", "value"),
    prevent_initial_call=True,
)
def handle_upload(contents, filename, source, mapping_text):
    if not contents:
        return no_update, no_update, no_update
    res = data_store.save_upload(contents, filename or "upload.csv", source, mapping_text)
    opts = [{"label": " Demo data (synthetic)", "value": "demo"},
            {"label": " Uploaded data", "value": "uploaded",
             "disabled": not data_store.has_uploaded()}]
    if not res["ok"]:
        msg = html.Div(f"✗ {res['error']}", style={"color": RED})
        return msg, opts, no_update
    rep, meta = res["report"], res["meta"]
    dropped = {k: v for k, v in rep.items()
               if k not in ("rows_in", "rows_out", "file") and v}
    msg = html.Div([
        html.Span(f"✓ {meta['filename']} loaded — {meta['rows']:,} clean rows, "
                  f"{meta['vessels']:,} vessels, {meta['t_min'][:16]} → {meta['t_max'][:16]}. ",
                  style={"color": GREEN}),
        html.Span(f"Quality report: {rep['rows_in']:,} in → {rep['rows_out']:,} out"
                  + (f" (dropped: {dropped})" if dropped else " (nothing dropped)"),
                  style={"color": TEXT2}),
    ])
    return msg, opts, "uploaded"


@app.callback(
    Output("map", "figure"), Output("kpis", "children"), Output("risk-table", "children"),
    Input("hour", "value"), Input("type-filter", "value"), Input("search", "value"),
    Input("data-mode", "value"), Input("upload-status", "children"),
    State("map", "figure"),
)
def update(hour, types, search_val, mode, _status, current_fig):
    center, zoom = None, None
    if search_val:
        _, lat, lon = search_val.split("|")
        center, zoom = {"lat": float(lat), "lon": float(lon)}, 10
    elif current_fig:
        mb = current_fig.get("layout", {}).get("mapbox", {})
        center, zoom = mb.get("center"), mb.get("zoom")

    if mode == "uploaded" and data_store.has_uploaded():
        fleet, dens, zones = data_store.load_snapshot(hour)
        src_label = "uploaded data"
        if center is None and len(fleet):
            center = {"lat": float(fleet.lat.mean()), "lon": float(fleet.lon.mean())}
            zoom = 8
    else:
        fleet, dens, zones = make_fleet(hour=hour), make_density_points(hour=hour), \
            make_risk_zones(hour=hour)
        src_label = "demo fleet"

    if types:
        fleet = fleet[fleet.vessel_type.isin(types)]

    kpis = [
        kpi_card("Total vessels", f"{len(fleet):,}", src_label),
        kpi_card("Avg speed", f"{fleet.sog.mean():.1f} kn" if len(fleet) else "—", "fleet mean"),
        kpi_card("Anchored", f"{(fleet.status == 'Anchored').sum()}", "SOG < 0.5 kn"),
        kpi_card("High-risk zones", f"{(zones.risk >= 0.8).sum() if len(zones) else 0}",
                 "risk ≥ 0.80"),
    ]

    if len(zones):
        header = html.Tr([html.Th(h, style={"textAlign": "left", "color": TEXT2,
                                            "fontSize": 11, "padding": "6px 12px"})
                          for h in ["ZONE", "RISK", "VESSELS", "D", "C", "K", "W", "G"]])
        rows = [html.Tr([
            html.Td(z.zone_id, style={"color": CYAN, "fontWeight": 600, "padding": "6px 12px"}),
            html.Td(f"{z.risk:.2f}", style={"color": RED if z.risk >= 0.8 else AMBER,
                                            "fontWeight": 700, "padding": "6px 12px"}),
            html.Td(f"{z.vessels:,}", style={"padding": "6px 12px"}),
            *[html.Td(f"{z[f]:.2f}", style={"color": TEXT2, "padding": "6px 12px"})
              for f in ["f_density", "f_crossing", "f_channel", "f_weather", "f_gaps"]],
        ]) for _, z in zones.sort_values("risk", ascending=False).iterrows()]
        note = ("Uploaded mode computes D and C from your file; K/W/G need the full "
                "pipeline's auxiliary data (coastline, weather, gap analysis) — see report §6."
                if mode == "uploaded" else "")
        table = html.Div([
            html.Div("HIGH RISK ZONES — five-factor breakdown (report §6.2)",
                     style={"fontSize": 12, "color": CYAN, "letterSpacing": "1px",
                            "margin": "8px 0"}),
            html.Table([header, *rows], style={"background": SURFACE, "borderRadius": 8,
                                               "width": "100%", "borderCollapse": "collapse"}),
            html.Div(note, style={"fontSize": 11, "color": TEXT2, "marginTop": 6}),
        ])
    else:
        table = html.Div("No risk zones for the current data/window.",
                         style={"color": TEXT2, "fontSize": 13})

    return build_map(fleet, dens, zones, center, zoom), kpis, table


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
