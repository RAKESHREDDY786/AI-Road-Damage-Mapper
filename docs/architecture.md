# System Architecture & Technical Specification

## Overview

**AI Road Damage Mapper** is a modular, multi-tier road condition monitoring platform.

This document details the system architecture, component responsibilities, the computer vision inference pipeline, the AI severity/priority engines, the GIS & analytics layer, and the deployment/security model.

---

## 1. High-Level System Architecture

```
+--------------------------------------------------------+
|                    FRONTEND LAYER                      |
|   HTML5 + Vanilla CSS3 + JavaScript (ES6 Modules/Fetch)|
+--------------------------------------------------------+
                           │
                           │ POST /analyze-image (Multipart)
                           ▼
+--------------------------------------------------------+
|                    FASTAPI BACKEND                     |
|   - Image Safety & Format Validation (Pillow/Size)     |
|   - Static Asset & Upload File Server                  |
|   - CORS & Environment Configuration                   |
+--------------------------------------------------------+
                           │
                           ▼
+--------------------------------------------------------+
|                   DETECTION SERVICE                    |
|   - Modular Computer Vision Inference Engine           |
|   - Model Lifecycle Management (Singleton)            |
|   - Bounding Box Localization (x1, y1, x2, y2)          |
|   - Centralized Class Name Mapping                      |
|   - Annotated Image Generator (ImageDraw)              |
+--------------------------------------------------------+
                           │
                           ▼
+--------------------------------------------------------+
|                    SEVERITY SERVICE                    |
|   - AI-Assisted Severity Heuristic Rules               |
|   - Damage Type Vulnerability Index                    |
|   - Bounding Box Frame Occupancy Ratio                |
|   - Outputs: LOW, MEDIUM, HIGH + Reason Rationale      |
+--------------------------------------------------------+
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
+-------------------------+   +--------------------------+
|    STRUCTURED RESULT    |   |     SQLITE DATABASE      |
|  - JSON API Response    |   |  - SQLAlchemy ORM        |
|  - Bounding Boxes       |   |  - Persistent Reports    |
|  - Severity Ratings     |   |  - Unassessed Support    |
+-------------------------+   +--------------------------+
```

---

## 2. Computer Vision & Severity Pipeline (Stage 2)

### A. Detection Service (`backend/services/detection_service.py`)
- **Model Loading**: Configured via `MODEL_PATH` and `CONFIDENCE_THRESHOLD` environment variables. Loads the model once at startup (singleton architecture).
- **Graceful Fallback**: If no model binary is present at `MODEL_PATH`, the service sets `model_status: "not_configured"` and returns empty detections `[]` without fabricating results or throwing runtime exceptions.
- **Class Mapping**: Centralized mapping table converting raw model classification tags/IDs (e.g. YOLO RDD2020 class indices `0`, `1`, `2`, `3`) to application damage types (`POTHOLE`, `LONGITUDINAL_CRACK`, `TRANSVERSE_CRACK`, `ALLIGATOR_CRACK`, `OTHER`).
- **Explicit Mode Flag**: Responses include `is_model_active` (true only when a real model produced the detections), so clients can distinguish real inference from the safe no-model path.
- **Annotation**: Generates color-coded annotated images (`<UPLOADS_DIR>/annotated_<uuid>.jpg`) with bounding box outlines and confidence tags using Pillow.

### B. Severity Estimation Service (`backend/services/severity_service.py`)
- **AI-Assisted Rules**: Computes severity levels (`LOW`, `MEDIUM`, `HIGH`) derived from:
  1. Base damage type vulnerability index (Potholes / Alligator cracks carry higher structural risk).
  2. Bounding box surface area relative to total image frame.
  3. Detection density (multiple detections escalate overall frame severity).
- *Disclaimer*: Severity scores provide automated triage prioritization and do not replace certified civil engineering site inspections.

### C. Maintenance Priority Service (`backend/services/priority_service.py`)
- **Deterministic Scoring**: Produces a 0–100 score from severity (≤45), damage-type vulnerability (≤20), confidence (≤10), damage-area/density (≤15), and GPS availability (≤10).
- **Categories**: `HIGH` (≥60), `MEDIUM` (≥35), `LOW` otherwise, with a human-readable rationale and a decision-support disclaimer.
- **Consumption**: The per-detection `area_ratio` is propagated into the API payload so `/analyze-image` and report creation compute consistent scores.

---

## 3. Data Flow Execution Sequence

1. User selects or drops an image in the **Analyze Road** tab of the frontend UI.
2. Frontend sends `multipart/form-data` request to `POST /analyze-image`.
3. Backend validates file extension (`.jpg`, `.jpeg`, `.png`, `.webp`), mime-type, max size (10MB limit), and Pillow binary readability.
4. Backend generates a secure UUID filename and stores the original image in `backend/uploads/`.
5. `DetectionService` performs model inference using `CONFIDENCE_THRESHOLD`.
6. For each detection, `SeverityService` calculates the individual and overall severity ratings.
7. An annotated image is generated and saved separately in `backend/uploads/`.
8. Backend returns structured JSON response with detections, severity ratings, coordinates, and annotated image path.
9. User can preview the results and click "Save Report to Database" to insert the report record into SQLite.

---

## 4. GIS, Analytics & Report Lifecycle (Stage 3)

- **GIS Map (`frontend/script.js`, Leaflet + OpenStreetMap)**: Renders geotagged reports as severity/priority-coloured circle markers with popups that open the report detail modal. Backed by `GET /reports` (client-side filtering) and `GET /reports/map`.
- **Analytics (`Chart.js` + `GET /analytics`)**: Damage-type, severity, priority, and workflow-status distributions plus a reports-over-time series. When the database is empty the UI shows an explicit empty state.
- **Report Lifecycle**: Reports can be created from an analysis result or manually, filtered, inspected, transitioned through `NEW → REVIEWED → RESOLVED`, and deleted (associated image files are removed with the row).
- **Workflow Status**: `PATCH /reports/{id}` re-evaluates the priority score after updates.

---

## 5. Deployment Topology (Stage 4)

- **Backend (Render)**: `render.yaml` provisions a Python web service from `rootDir: backend`, installs `requirements.txt`, and runs Gunicorn with a Uvicorn worker bound to `0.0.0.0:$PORT`.
- **Persistence**: SQLite and uploaded images live on a Render persistent disk mounted at `/data` (`DATABASE_URL=sqlite:////data/road_damage.db`, `UPLOADS_DIR=/data/uploads`). Disks require a paid instance type; the free tier instead uses a managed database (e.g. Postgres) and external object storage.
- **Frontend**: Either served same-origin by the backend (`/app`) or deployed separately with the backend origin supplied via the `<meta name="api-base-url">` tag; that origin is then added to `FRONTEND_ORIGIN`.
- **Local development is unaffected**: defaults fall back to `backend/uploads/` and `sqlite:///./road_damage.db`.

---

## 6. Security & Configuration (Stage 5)

- **Optional write protection**: When `API_KEY` is set, `POST`/`PATCH`/`DELETE` require the `X-API-Key` header (`require_api_key` dependency). Empty (default) leaves writes open for local use. No secrets are stored in the repository.
- **Upload safety**: Content type, extension, size (≤10 MB), and Pillow readability are validated; storage uses random UUID filenames to prevent path traversal/overwrite.
- **CORS**: Production origins come from `FRONTEND_ORIGIN`; a narrow regex allows any `localhost`/`127.0.0.1` port for local development. Wildcards are never combined with credentials.
- **Error handling**: Clients receive concise JSON error details; internal stack traces and environment secrets are not exposed.
- **Testing**: `backend/tests/` spins up a real server and validates behaviour (health, CRUD, validation, image analysis/no-model, API-key enforcement) using only the standard library. The default fixtures force no-model mode (`MODEL_PATH=""`) so the suite is hermetic regardless of local `.env`; `tests/test_model_mode.py` additionally validates the real inference contract and is auto-skipped when weights or Ultralytics are unavailable.
