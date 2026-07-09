"""Source adapters — one small class per AIS data source.

An adapter's ONLY job is to translate a source file into the canonical
schema (pipeline.schema). It handles column names, units, timestamp
formats, sentinel conventions, and vessel-type vocabulary. Shared
validation happens AFTER adaptation, identically for every source.

Adding a new source = adding ~20 lines here (or just a JSON mapping file
for the GenericCSVAdapter). Nothing downstream changes. This is what
makes the platform hot-swappable across historical datasets and, later,
a live feed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.schema import class_from_ais_code, coerce

ADAPTERS: dict[str, type] = {}


def register(name: str):
    def deco(cls):
        ADAPTERS[name] = cls
        return cls
    return deco


class BaseAdapter:
    """Subclass and implement to_canonical(raw_df) -> canonical df."""

    #: columns to request from the CSV reader (None = all)
    usecols: list[str] | None = None

    def read(self, path: str | Path, nrows: int | None = None) -> pd.DataFrame:
        raw = pd.read_csv(path, usecols=self.usecols, nrows=nrows)
        return coerce(self.to_canonical(raw))

    def to_canonical(self, raw: pd.DataFrame) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError


@register("noaa")
class NoaaMarineCadastreAdapter(BaseAdapter):
    """NOAA MarineCadastre daily AIS CSV (2015+ schema).

    Columns: MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName,
    IMO, CallSign, VesselType (numeric code), Status, Length, Width, Draft, ...
    Timestamps are UTC without timezone suffix. Units already knots/degrees/metres.
    """

    usecols = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading",
               "VesselName", "IMO", "CallSign", "VesselType", "Status",
               "Length", "Width", "Draft"]

    def to_canonical(self, raw: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "mmsi": pd.to_numeric(raw["MMSI"], errors="coerce"),
            "ts": pd.to_datetime(raw["BaseDateTime"], utc=True, errors="coerce"),
            "lat": raw["LAT"], "lon": raw["LON"],
            "sog": raw["SOG"], "cog": raw["COG"], "heading": raw["Heading"],
            "nav_status": pd.to_numeric(raw.get("Status"), errors="coerce"),
            "vessel_class": raw["VesselType"].map(class_from_ais_code),
            "name": raw.get("VesselName"), "imo": raw.get("IMO"),
            "callsign": raw.get("CallSign"),
            "length": raw.get("Length"), "width": raw.get("Width"),
            "draft": raw.get("Draft"),
        })


@register("dma")
class DanishDmaAdapter(BaseAdapter):
    """Danish Maritime Authority aisdk daily CSV (web.ais.dk).

    Columns: '# Timestamp' (dd/mm/yyyy HH:MM:SS), 'MMSI', 'Latitude',
    'Longitude', 'SOG', 'COG', 'Heading', 'Ship type' (string vocabulary),
    'Navigational status' (string), 'Name', 'IMO', 'Callsign', dimensions.
    """

    TYPE_MAP = {
        "Cargo": "Cargo", "Tanker": "Tanker", "Passenger": "Passenger",
        "Fishing": "Fishing", "Tug": "Tug", "Towing": "Tug",
        "Military": "Military", "Sailing": "Sailing", "Pleasure": "Pleasure",
        "HSC": "HSC",
    }
    STATUS_MAP = {
        "Under way using engine": 0, "At anchor": 1, "Not under command": 2,
        "Restricted maneuverability": 3, "Constrained by her draught": 4,
        "Moored": 5, "Aground": 6, "Engaged in fishing": 7,
        "Under way sailing": 8,
    }

    def to_canonical(self, raw: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "mmsi": pd.to_numeric(raw["MMSI"], errors="coerce"),
            "ts": pd.to_datetime(raw["# Timestamp"], format="%d/%m/%Y %H:%M:%S",
                                 utc=True, errors="coerce"),
            "lat": raw["Latitude"], "lon": raw["Longitude"],
            "sog": raw["SOG"], "cog": raw["COG"], "heading": raw["Heading"],
            "nav_status": raw.get("Navigational status", pd.Series(dtype=object))
                              .map(self.STATUS_MAP),
            "vessel_class": raw.get("Ship type", pd.Series(dtype=object))
                                .map(self.TYPE_MAP).fillna("Other"),
            "name": raw.get("Name"), "imo": raw.get("IMO"),
            "callsign": raw.get("Callsign"),
            "length": raw.get("Length"), "width": raw.get("Width"),
            "draft": raw.get("Draught"),
        })


@register("generic")
class GenericCSVAdapter(BaseAdapter):
    """Config-driven adapter: ingest ANY AIS CSV via a JSON mapping file.

    Mapping file example (pipeline/mappings/example_mapping.json):
    {
      "columns": {"mmsi": "MMSI", "ts": "time", "lat": "latitude",
                   "lon": "longitude", "sog": "speed", "cog": "course",
                   "heading": "hdg", "name": "shipname",
                   "vessel_class": "shiptype"},
      "ts_format": null,                # null -> pandas auto-parse
      "ts_unit": null,                  # "s"/"ms" for epoch timestamps
      "sog_unit": "knots",              # or "ms" (metres/second) / "kmh"
      "vessel_class_is_ais_code": true  # numeric ITU codes vs free text
    }
    """

    def __init__(self, mapping_path: str | Path):
        self.cfg = json.loads(Path(mapping_path).read_text())

    def to_canonical(self, raw: pd.DataFrame) -> pd.DataFrame:
        cols = self.cfg["columns"]
        out = pd.DataFrame()
        for canon, source in cols.items():
            if source in raw.columns:
                out[canon] = raw[source]

        # timestamp
        if self.cfg.get("ts_unit"):
            out["ts"] = pd.to_datetime(out["ts"], unit=self.cfg["ts_unit"], utc=True)
        else:
            out["ts"] = pd.to_datetime(out["ts"], format=self.cfg.get("ts_format"),
                                       utc=True, errors="coerce")
        # speed unit conversion -> knots
        unit = self.cfg.get("sog_unit", "knots")
        if "sog" in out:
            if unit == "ms":
                out["sog"] = out["sog"] * 1.94384
            elif unit == "kmh":
                out["sog"] = out["sog"] * 0.539957
        # vessel class vocabulary
        if "vessel_class" in out and self.cfg.get("vessel_class_is_ais_code"):
            out["vessel_class"] = out["vessel_class"].map(class_from_ais_code)
        out["mmsi"] = pd.to_numeric(out.get("mmsi"), errors="coerce")
        return out


def get_adapter(source: str, mapping: str | None = None) -> BaseAdapter:
    if source == "generic":
        if not mapping:
            raise ValueError("generic source requires --mapping <file.json>")
        return GenericCSVAdapter(mapping)
    if source not in ADAPTERS:
        raise ValueError(f"unknown source '{source}'; available: {list(ADAPTERS)}")
    return ADAPTERS[source]()
