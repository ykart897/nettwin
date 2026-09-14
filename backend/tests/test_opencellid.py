from app.telemetry.opencellid import OpenCellIdProvider


def test_opencellid_import_filters_to_istanbul_and_turkey(tmp_path):
    path = tmp_path / "cells.csv"
    path.write_text(
        "radio,mcc,net,area,cell,lon,lat,samples,averageSignal,updated\n"
        "LTE,286,1,10,100,29.01,41.03,5,-91,1710000000\n"
        "LTE,286,1,10,101,32.85,39.93,5,-85,1710000000\n"
        "LTE,262,1,10,102,29.01,41.03,5,-80,1710000000\n",
        encoding="utf-8",
    )

    result = OpenCellIdProvider(str(path)).sync()

    assert result.configured is True
    assert len(result.assets) == 1
    assert result.assets[0]["external_id"] == "286-1-10-100"
    assert len(result.observations) == 1
    assert result.observations[0]["signal_strength_dbm"] == -91


def test_missing_opencellid_file_is_unconfigured(tmp_path):
    result = OpenCellIdProvider(str(tmp_path / "missing.csv.gz")).sync()

    assert result.configured is False
    assert "not found" in result.message.lower()
