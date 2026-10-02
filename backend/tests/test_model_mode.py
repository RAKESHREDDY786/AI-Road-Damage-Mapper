"""Model-mode behaviour: the app must never fabricate detections.

These tests only run when real weights and the Ultralytics extra are present
(see the `api_with_model` fixture in conftest.py); otherwise they skip. They
assert the *contract* around a configured model rather than exact detection
counts, so they stay valid for any weights file.
"""
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BACKEND_DIR, "uploads")


def _cleanup_uploads(body):
    for rel in (body.get("original_image"), body.get("annotated_image")):
        if not rel:
            continue
        path = os.path.join(UPLOADS_DIR, os.path.basename(rel))
        if os.path.exists(path):
            os.remove(path)


def test_health_reports_valid_model_status(api_with_model):
    status, body = api_with_model.get("/health")
    assert status == 200
    assert body["model_status"] in {"available", "not_configured", "failed_to_load"}


def test_configured_model_loads_available(api_with_model):
    # With weights present and Ultralytics installed the model must load cleanly.
    status, body = api_with_model.get("/health")
    assert status == 200
    assert body["model_status"] == "available"


def test_truthful_model_flag_and_no_fabrication(api_with_model, sample_image_bytes):
    status, body = api_with_model.post_file(
        "/analyze-image", "file", "road.jpg", "image/jpeg", sample_image_bytes
    )
    assert status == 200
    assert body["success"] is True

    try:
        if body["is_model_active"]:
            # A real model produced the results: the status must agree and any
            # detections must be well-formed.
            assert body["model_status"] == "available"
            assert isinstance(body["detections"], list)
            for det in body["detections"]:
                assert 0.0 <= det["confidence"] <= 1.0
                assert set(det["bounding_box"]) == {"x1", "y1", "x2", "y2"}
                assert det["severity"] in {"LOW", "MEDIUM", "HIGH"}
            assert body["priority_level"] in {"LOW", "MEDIUM", "HIGH"}
        else:
            # No model produced results -> detections must be empty, never invented.
            assert body["detections"] == []
            assert len(body["warnings"]) >= 1
    finally:
        _cleanup_uploads(body)