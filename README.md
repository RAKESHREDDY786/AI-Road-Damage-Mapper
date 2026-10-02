# AI Road Damage Mapper (Stage 2 Computer Vision)

AI-assisted road damage detection, mapping, and maintenance prioritization system.

---

## Project Purpose

Road infrastructure deteriorates over time with potholes, cracks, and structural wear. **AI Road Damage Mapper** automates the lifecycle of road condition monitoring:

`Road Image / Video` ➔ `AI Computer Vision Detection` ➔ `Damage Classification` ➔ `Severity Estimation` ➔ `Geospatial Mapping` ➔ `Maintenance Prioritization`

This Stage 2 release integrates a **modular computer vision detection service, AI severity estimation engine, bounding box annotation generator, and `POST /analyze-image` REST endpoint**, building directly on the Stage 1 database foundation.

---

## Stage 2 Features

- **Computer Vision Detection Service**: Modular inference pipeline (`backend/services/detection_service.py`) supporting YOLO / PyTorch / OpenCV DNN model architectures.
- **AI Severity Engine**: Heuristic severity scoring (`backend/services/severity_service.py`) analyzing damage type vulnerability, relative bounding box surface area, and distress density (`LOW`, `MEDIUM`, `HIGH`).
- **Bounding Box Annotation**: Draws color-coded bounding boxes and confidence labels on images using Pillow, preserving the original upload.
- **Centralized Class Mapping**: Flexible dictionary mapping raw model class names/indices to application damage categories (`POTHOLE`, `LONGITUDINAL_CRACK`, `TRANSVERSE_CRACK`, `ALLIGATOR_CRACK`, `OTHER`).
- **No Fabricated AI Data**: If `MODEL_PATH` is unconfigured or a model file is not provided, the application reports `model_status: "not_configured"` cleanly with empty detections `[]` and explicit setup warnings.
- **`POST /analyze-image` API**: Full image analysis REST endpoint.
- **Frontend Analysis Interface**: Drag-and-drop dropzone, live image preview, inference loading spinner, model status badge, annotated vs. original image comparison, and database saving workflow.

---

## Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Computer Vision**: Pillow (PIL), Ultralytics YOLO / OpenCV DNN
- **Validation**: Pydantic v2
- **Database**: SQLite, SQLAlchemy ORM
- **Frontend**: HTML5, Vanilla CSS3, JavaScript (ES6 `fetch` API)
- **Environment**: `python-dotenv`

---

## Project Folder Structure

```
AI-Road-Damage-Mapper/
│
├── frontend/
│   ├── index.html       # Single-page interface with Analyze Road computer vision tab
│   ├── style.css        # Responsive dark slate design & comparison grid styles
│   └── script.js        # API integration, live image preview, AI rendering & DB saving
│
├── backend/
│   ├── main.py          # FastAPI application & REST endpoint handlers
│   ├── database.py      # SQLAlchemy engine and DB session setup
│   ├── models.py        # SQLAlchemy models and Enum definitions
│   ├── schemas.py       # Pydantic validation schemas & AI response models
│   ├── requirements.txt # Python dependencies
│   ├── uploads/         # Safe storage for uploaded original & annotated images
│   └── services/
│       ├── detection_service.py # Model loading, inference, & annotation
│       └── severity_service.py  # AI-assisted severity rules engine
│
├── models/
│   └── README.md        # Folder for computer vision model binaries (.pt / .onnx)
│
├── data/
│   └── README.md        # Reserved folder for sample road image datasets
│
├── docs/
│   └── architecture.md  # Detailed architecture documentation & AI pipeline flow
│
├── .env.example         # Environment configuration placeholders
├── .gitignore           # Git ignore rules for DB, cache, and virtualenv
└── README.md            # Comprehensive project documentation
```

---

## Model Configuration & Behavior

Configure model parameters in `.env`:

```env
MODEL_PATH=models/yolov8_road_damage.pt
CONFIDENCE_THRESHOLD=0.5
```

### Model Status Behavior
- **`available`**: Model binary exists at `MODEL_PATH` and loaded successfully. Inference produces bounding boxes and damage predictions.
- **`not_configured`**: `MODEL_PATH` is empty or the model file does not exist. The server starts normally, returns `model_status: "not_configured"`, empty detections `[]`, and helpful setup instructions. **No fake predictions are ever generated.**
- **`failed_to_load`**: Model file exists but failed to initialize. Handled gracefully with explicit diagnostic warnings.

---

## API Endpoint Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API status, version, and model status |
| `GET` | `/health` | Health check endpoint (DB & Model status) |
| `POST` | `/analyze-image` | Upload road image for computer vision detection & severity analysis |
| `POST` | `/reports` | Create a new road damage report (JSON payload) |
| `POST` | `/reports/upload` | Create report with optional image file upload |
| `GET` | `/reports` | Retrieve list of reports (supports filter by status, damage_type, severity) |
| `GET` | `/reports/{id}` | Get details of a single report by ID |
| `PATCH`| `/reports/{id}` | Update report fields (e.g. status, severity) |
| `DELETE`| `/reports/{id}`| Delete a report and remove associated stored image |
| `GET` | `/statistics` | Return damage report statistics and counts |

### `POST /analyze-image` Details

- **Accepted File Formats**: `JPG`, `JPEG`, `PNG`, `WEBP` (Max size: 10MB)
- **Request Format**: `multipart/form-data` with `file` field.
- **Response Format**:
```json
{
  "success": true,
  "model_status": "available",
  "detections": [
    {
      "damage_type": "POTHOLE",
      "confidence": 0.91,
      "bounding_box": {
        "x1": 120.0,
        "y1": 150.0,
        "x2": 450.0,
        "y2": 380.0
      },
      "severity": "HIGH",
      "severity_reason": "High severity: Critical pothole occupying 12.5% of image frame."
    }
  ],
  "overall_severity": "HIGH",
  "annotated_image": "uploads/annotated_a1b2c3d4.jpg",
  "original_image": "uploads/damage_e5f6g7h8.jpg",
  "warnings": []
}
```

---

## Installation & Setup Guide

### 1. Create & Activate Virtual Environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure `.env`
```bash
cp .env.example .env
```

### 4. Start FastAPI Server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### 5. Open Frontend UI
- Direct Browser URL: Open `http://localhost:8000/` in browser.
- Double-click `frontend/index.html`.

---

## Future Development Stages

- **Stage 3**: Integrate Leaflet/OpenStreetMap interactive GIS map view, GPS coordinate pin plotting, regional damage heatmaps, and automated maintenance priority score calculation engine.
