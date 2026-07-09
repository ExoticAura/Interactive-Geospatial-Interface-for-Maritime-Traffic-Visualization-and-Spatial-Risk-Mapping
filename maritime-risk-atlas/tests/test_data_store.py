import base64

from app import data_store

NOAA_CSV = (
    "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,"
    "VesselType,Status,Length,Width,Draft\n"
    + "\n".join(
        f"56301{i:04d},2024-07-01T{h:02d}:00:03,{1.20+i*0.001},{103.84+i*0.001},"
        f"12.4,215.0,214.0,SHIP {i},,,71,0,300,48,14.5"
        for i in range(30) for h in (0, 12)
    )
)


def _b64(text: str) -> str:
    return "data:text/csv;base64," + base64.b64encode(text.encode()).decode()


def test_upload_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(data_store, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(data_store, "UPLOAD_PARQUET", tmp_path / "u.parquet")
    monkeypatch.setattr(data_store, "UPLOAD_META", tmp_path / "u.meta.json")

    res = data_store.save_upload(_b64(NOAA_CSV), "sample.csv", "noaa", None)
    assert res["ok"], res
    assert data_store.has_uploaded()

    fleet, dens, zones = data_store.load_snapshot(hour=12)
    assert len(fleet) == 30           # one latest fix per vessel
    assert len(dens) >= 30
    assert set(fleet.status.unique()) <= {"Underway", "Anchored"}


def test_upload_rejects_non_csv():
    res = data_store.save_upload(_b64("x"), "data.xlsx", "noaa", None)
    assert not res["ok"] and "csv" in res["error"].lower()


def test_generic_requires_mapping():
    res = data_store.save_upload(_b64("a,b\n1,2"), "f.csv", "generic", None)
    assert not res["ok"] and "mapping" in res["error"].lower()
