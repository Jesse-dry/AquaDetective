"""Unified public-data ingest contract tests."""
from __future__ import annotations

import pandas as pd

from app.ingest import mappers, schema


def test_taihu_observations_and_evaluation_labels_are_isolated():
    frame = pd.DataFrame(
        {
            "ts": ["2022-12-02T12:00:00+08:00", "invalid"],
            "ammonia_n": [0.698, 0.4],
            "codmn": [5.2, None],
            "quality_class": ["III", "IV"],
        }
    )

    observations = mappers.map_taihu_reading_frame(frame, "taihu_059")
    labels = mappers.map_taihu_evaluation_labels(frame, "taihu_059")

    assert list(observations.columns) == schema.OBSERVATION_COLUMNS
    assert set(observations["parameter_code"]) == {"ammonia_n", "codmn"}
    assert set(observations["timestamp_utc"]) == {"2022-12-02T04:00:00Z"}
    assert "quality_class" not in observations.columns
    assert "truth_source" not in observations.columns
    assert list(labels.columns) == schema.EVALUATION_LABEL_COLUMNS
    assert labels.to_dict("records") == [
        {
            "dataset_id": "guokong_surface_water_2021_2025",
            "station_id": "guokong_surface_water_2021_2025:taihu_059",
            "timestamp_utc": "2022-12-02T04:00:00Z",
            "label_code": "quality_class",
            "label_value": "III",
            "label_source": "CNEMC published water-quality class",
        }
    ]


def test_network_ids_are_generic_for_us_and_taihu_sites(tmp_path):
    us_path = tmp_path / "us_sites.csv"
    pd.DataFrame(
        [
            {
                "dataset": "wqp",
                "source_id": "USGS-1",
                "name": "Station",
                "site_type": "Stream",
                "provider": "NWIS",
                "lat": 41.0,
                "lon": -81.0,
                "COMID": 60001200051917,
                "snap_dist_m": 12.0,
                "snap_flag": "ok",
            }
        ]
    ).to_csv(us_path, index=False)

    taihu_path = tmp_path / "taihu_sites.csv"
    pd.DataFrame(
        [
            {
                "station_id": "taihu_001",
                "name": "Station",
                "lon_wgs": 120.0,
                "lat_wgs": 31.0,
                "hyriv_id": 40636807,
                "snap_dist_m": 20.0,
                "matched": True,
            }
        ]
    ).to_csv(taihu_path, index=False)

    us = mappers.map_sites(us_path)
    taihu = mappers.map_taihu_sites(taihu_path)

    assert list(us.columns) == schema.SITE_COLUMNS
    assert list(taihu.columns) == schema.SITE_COLUMNS
    assert us.loc[0, ["network_id", "reach_id"]].tolist() == [
        "nhdplus_hr_cuyahoga",
        "60001200051917",
    ]
    assert taihu.loc[0, ["network_id", "reach_id"]].tolist() == [
        "hydrorivers_v10_as",
        "40636807",
    ]
    assert "comid" not in schema.SITE_COLUMNS


def test_us_flow_uses_generic_network_contract(tmp_path):
    path = tmp_path / "flow.csv"
    pd.DataFrame(
        [{"COMID": 10, "FromNode": 1, "ToNode": 2, "LengthKM": 1.5}]
    ).to_csv(path, index=False)

    flow = mappers.map_flow(path)

    assert list(flow.columns) == schema.FLOW_COLUMNS
    assert flow.loc[0, "network_id"] == "nhdplus_hr_cuyahoga"
    assert flow.loc[0, "reach_id"] == "10"
    assert pd.isna(flow.loc[0, "downstream_reach_id"])


def test_taihu_facilities_have_unique_ids_when_registration_is_shared(tmp_path):
    path = tmp_path / "taihu_sources.csv"
    rows = []
    for name in ("North Plant", "South Plant"):
        rows.append(
            {
                "credit_code": "91320000TEST",
                "name": name,
                "industry": "wwtp",
                "city": "Wuxi",
                "address": "Shared registered address",
                "lat_wgs84": 31.6,
                "lon_wgs84": 120.4,
                "hyriv_id": 40625635,
                "matched": True,
                "snap_dist_m": 10.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)

    first = mappers.map_taihu_sources(path)
    second = mappers.map_taihu_sources(path)

    assert first["source_id"].is_unique
    assert first["source_id"].tolist() == second["source_id"].tolist()
    assert first["registration_id"].tolist() == ["91320000TEST", "91320000TEST"]
