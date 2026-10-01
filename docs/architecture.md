# System Architecture & Technical Specification

## Overview

**AI Road Damage Mapper** is a modular, multi-tier road condition monitoring platform.

This document details the system architecture, component responsibilities, computer vision inference pipeline, and AI severity estimation engine.

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
- **Annotation**: Generates color-coded annotated images (`backend/uploads/annotated_<uuid>.jpg`) with bounding box outlines and confidence tags using Pillow.

### B. Severity Estimation Service (`backend/services/severity_service.py`)
- **AI-Assisted Rules**: Computes severity levels (`LOW`, `MEDIUM`, `HIGH`) derived from:
  1. Base damage type vulnerability index (Potholes / Alligator cracks carry higher structural risk).
  2. Bounding box surface area relative to total image frame.
  3. Detection density (multiple detections escalate overall frame severity).
- *Disclaimer*: Severity scores provide automated triage prioritization and do not replace certified civil engineering site inspections.

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
