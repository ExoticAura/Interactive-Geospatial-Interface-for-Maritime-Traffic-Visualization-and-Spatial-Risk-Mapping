import io
import pandas as pd
import pytest

from pipeline.adapters import DanishDmaAdapter, GenericCSVAdapter, NoaaMarineCadastreAdapter
from pipeline.schema import CANONICAL_COLUMNS, coerce, validate

NOAA_CSV = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
563017000,2024-07-01T00:00:03,1.2011,103.8412,12.4,215.0,214.0,EVER DEMO,IMO1234567,9V1234,71,0,300,48,14.5
367001234,2024-07-01T00:00:07,33.7291,-118.2620,0.1,360.0,511.0,ANCHOR QUEEN,,,80,1,250,40,12.0
0,2024-07-01T00:00:09,91.0,181.0,102.3,360.0,511.0,BAD ROW,,,99,15,,,
"""

DMA_CSV = """# Timestamp,Type of mobile,MMSI,Latitude,Longitude,Navigational status,SOG,COG,Heading,Ship type,Name,IMO,Callsign,Length,Width,Draught
01/07/2024 00:00:01,Class A,219000111,55.5000,12.6000,Under way using engine,14.2,90.0,91.0,Cargo,DEMO DANE,IMO7654321,OU1234,180,28,9.5
"""

GEN_CSV = """MMSI,time,latitude,longitude,speed,course,hdg,shipname,shiptype
205123456,2024-07-01 00:00:05,1.15,103.7,6.3,120,121,GEN SHIP,70
"""


def test_noaa_adapter_and_validation():
    df = NoaaMarineCadastreAdapter().to_canonical(pd.read_csv(io.StringIO(NOAA_CSV)))
    df = coerce(df)
    clean, rep = validate(df)
    assert list(clean.columns) == list(CANONICAL_COLUMNS)
    assert len(clean) == 2                    # bad row dropped
    assert rep["bad_coords"] + rep["bad_mmsi"] >= 1
    row = clean.iloc[0]
    assert row.vessel_class == "Cargo" and str(row.ts.tz) == "UTC"
    # sentinel handling: COG 360 / heading 511 -> NaN
    anchored = clean.iloc[1]
    assert pd.isna(anchored.cog) and pd.isna(anchored.heading)
    assert anchored.vessel_class == "Tanker" and anchored.nav_status == 1


def test_dma_adapter():
    df = coerce(DanishDmaAdapter().to_canonical(pd.read_csv(io.StringIO(DMA_CSV))))
    clean, _ = validate(df)
    assert len(clean) == 1
    r = clean.iloc[0]
    assert r.vessel_class == "Cargo" and r.nav_status == 0 and r.mmsi == 219000111


def test_generic_adapter(tmp_path):
    m = tmp_path / "map.json"
    m.write_text('{"columns":{"mmsi":"MMSI","ts":"time","lat":"latitude",'
                 '"lon":"longitude","sog":"speed","cog":"course","heading":"hdg",'
                 '"name":"shipname","vessel_class":"shiptype"},'
                 '"sog_unit":"knots","vessel_class_is_ais_code":true}')
    df = coerce(GenericCSVAdapter(m).to_canonical(pd.read_csv(io.StringIO(GEN_CSV))))
    clean, _ = validate(df)
    assert len(clean) == 1 and clean.iloc[0].vessel_class == "Cargo"


def test_same_schema_across_sources():
    a = coerce(NoaaMarineCadastreAdapter().to_canonical(pd.read_csv(io.StringIO(NOAA_CSV))))
    b = coerce(DanishDmaAdapter().to_canonical(pd.read_csv(io.StringIO(DMA_CSV))))
    assert list(a.columns) == list(b.columns)  # the hot-swap guarantee
