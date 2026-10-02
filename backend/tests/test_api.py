"""Behavioural tests for the core API endpoints (local, no-model configuration).

These run against a live server (see conftest.py) and use resource-independent
assertions so they pass on an empty or populated database.
"""
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BACKEND_DIR, "uploads")


def test_health_reports_database_connected(api):
    status, body = api.get("/health")
    assert status == 200
    assert body["database"] == "connected"
    assert body["status"] in {"healthy", "degraded"}
    assert body["model_status"] in {"available", "not_configured", "failed_to_load"}


def test_statistics_has_expected_shape(api):
    status, body = api.get("/statistics")
    assert status == 200
    for key in ("total_reports", "by_damage_type", "by_severity", "by_status", "average_priority_score"):
        assert key in body


def test_reports_crud_roundtrip(api):
    payload = {
        "damage_type": "POTHOLE",
        "severity": "HIGH",
        "latitude": 10.0,
        "longitude": 20.0,
        "description": "pytest CRUD record",
    }
    status, data = api.post_json("/reports", payload)
    assert status == 201
    report_id = data["id"]
    # HIGH severity + POTHOLE must land in the HIGH priority band
    assert data["priority_level"] == "HIGH"
    assert data["priority_score"] >= 60.0

    try:
        status, got = api.get("/reports/%d" % report_id)
        assert status == 200
        assert got["description"] == "pytest CRUD record"

        status, patched = api.patch_json("/reports/%d" % report_id, {"status": "RESOLVED"})
        assert status == 200
        assert patched["status"] == "RESOLVED"

        status, listed = api.get("/reports?limit=500")
        assert status == 200
        assert any(r["id"] == report_id for r in listed)
    finally:
        assert api.delete("/reports/%d" % report_id)[0] == 200

    assert api.get("/reports/%d" % report_id)[0] == 404


def test_create_report_rejects_out_of_range_latitude(api):
    status, _ = api.post_json("/reports", {"latitude": 999.0})
    assert status == 422


def test_missing_report_returns_404(api):
    assert api.get("/reports/987654321")[0] == 404


def test_map_endpoint_returns_list(api):
    status, body = api.get("/reports/map")
    assert status == 200
    assert isinstance(body, list)


def test_analytics_endpoint_has_timeseries(api):
    status, body = api.get("/analytics")
    assert status == 200
    assert "has_data" in body
    assert isinstance(body["reports_over_time"], list)


def test_analyze_image_in_no_model_mode(api, sample_image_bytes):
    status, body = api.post_file(
        "/analyze-image", "file", "road.jpg", "image/jpeg", sample_image_bytes
    )
    assert status == 200
    assert body["success"] is True
    assert body["model_status"] == "not_configured"
    assert body["is_model_active"] is False
    assert body["detections"] == []          # never fabricates results
    assert body["priority_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert len(body["warnings"]) >= 1

    saved_path = os.path.join(UPLOADS_DIR, os.path.basename(body["original_image"]))
    assert os.path.exists(saved_path)
    os.remove(saved_path)  # keep the working tree clean


def test_analyze_image_rejects_unsupported_file_type(api):
    status, _ = api.post_file("/analyze-image", "file", "notes.txt", "text/plain", b"not an image")
    assert status == 400


def test_analyze_image_rejects_corrupt_image(api):
    status, _ = api.post_file("/analyze-image", "file", "fake.jpg", "image/jpeg", b"still not an image")
    assert status == 400