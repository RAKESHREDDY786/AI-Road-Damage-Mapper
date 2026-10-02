# AI Road Damage Mapper

AI-assisted road damage detection, GIS mapping, and maintenance prioritization system.

---

## Project Purpose

Road infrastructure deteriorates over time with potholes, cracks, and structural wear. **AI Road Damage Mapper** automates the lifecycle of road condition monitoring:

`Road Image` ➔ `AI Computer Vision Detection` ➔ `Damage Classification` ➔ `Severity + Priority Estimation` ➔ `Geospatial Mapping` ➔ `Analytics & Report Management`

A single FastAPI backend also serves a vanilla-JS single-page frontend. It provides image upload & analysis, an AI severity/priority engine, a Leaflet/OpenStreetMap GIS view, Chart.js analytics, and full report lifecycle management on SQLite.

---

## Features

- **Computer Vision Detection Service**: Modular inference pipeline (`backend/services/detection_service.py`) supporting Ultralytics YOLO (`.pt`) and an OpenCV DNN fallback (`.onnx`).
- **AI Severity Engine**: Heuristic severity scoring (`backend/services/severity_service.py`) combining damage-type vulnerability, bounding-box frame occupancy, and detection density (`LOW`, `MEDIUM`, `HIGH`).
- **Maintenance Priority Engine**: Deterministic 0–100 priority score (`backend/services/priority_service.py`) from severity, damage type, confidence, damage area, detection count, and GPS availability.
- **Bounding Box Annotation**: Draws color-coded bounding boxes and confidence labels with Pillow, preserving the original upload.
- **Centralized Class Mapping**: Maps raw model class names/indices to app categories (`POTHOLE`, `LONGITUDINAL_CRACK`, `TRANSVERSE_CRACK`, `ALLIGATOR_CRACK`, `OTHER`, `NO_DAMAGE`).
- **No Fabricated AI Data**: With no model configured the API reports `model_status: "not_configured"` and `is_model_active: false` with empty detections `[]` — it never invents results.
- **Interactive GIS Map**: Leaflet + OpenStreetMap pins coloured by severity/priority, with popups linking to full report details.
- **Analytics Dashboard**: Real database statistics and Chart.js charts (damage type, severity, priority, workflow status, ingestion timeline).
- **Report Lifecycle**: Create (from analysis or manually), filter, inspect, update workflow status, and delete reports; associated image files are cleaned up on delete.
- **Optional write protection**: A configurable API key guards all data-changing endpoints without complicating local development.
- **Reusable test suite**: `backend/tests/` runs behavioural tests against a live server using only the standard library.

---

## Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn (production: Gunicorn + Uvicorn worker)
- **Computer Vision**: Pillow (PIL); optional Ultralytics YOLO / OpenCV DNN
- **Validation**: Pydantic v2
- **Database**: SQLite + SQLAlchemy ORM (or any SQLAlchemy URL, e.g. Postgres)
- **Frontend**: HTML5, Vanilla CSS3, JavaScript (ES6 `fetch`), Leaflet.js, Chart.js
- **Environment**: `python-dotenv`
- **Testing**: pytest (behavioural tests over HTTP, standard library only)

---

## Project Folder Structure

```
AI-Road-Damage-Mapper/
│
├── frontend/
│   ├── index.html       # Single-page interface (Dashboard, Analyze, Reports, Map, Analytics, About)
│   ├── style.css        # Responsive dark slate design
│   └── script.js        # API integration, GIS map, charts, report lifecycle
│
├── backend/
│   ├── main.py          # FastAPI application & REST endpoint handlers
│   ├── database.py      # SQLAlchemy engine, session, and SQLite migrations
│   ├── models.py        # SQLAlchemy models and Enum definitions
│   ├── schemas.py       # Pydantic validation & API response models
│   ├── requirements.txt    # Core Python dependencies
│   ├── requirements-ai.txt # Optional AI/CV dependencies (ultralytics, opencv, numpy)
│   ├── pytest.ini       # Pytest configuration
│   ├── tests/           # Behavioural API tests (conftest + test modules)
│   ├── uploads/         # Storage for uploaded original & annotated images
│   └── services/
│       ├── detection_service.py # Model loading, inference, & annotation
│       ├── severity_service.py  # AI-assisted severity rules engine
│       └── priority_service.py  # Deterministic maintenance-priority engine
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
├── render.yaml          # Render deployment blueprint (backend web service)
└── README.md            # Comprehensive project documentation
```

---

## Model Configuration & Behavior

Configure model parameters in `.env`:

```env
MODEL_PATH=models/yolov8_road_damage.pt
CONFIDENCE_THRESHOLD=0.5
```

> **Bundled model note**: this repository ships `models/best.pt`, a lightweight
> 4-class road-damage model (`longitudinal_crack`, `transverse_crack`,
> `alligator_crack`, `pothole`). It emits detections at roughly **~0.25**
> confidence, so the local `.env` sets `CONFIDENCE_THRESHOLD=0.25` — with the
> code default of `0.5` its real detections would be filtered out. Raise the
> threshold for stricter, higher-precision output or when swapping in a stronger model.

### Model Status Behavior
- **`available`**: Model binary exists at `MODEL_PATH` and loaded successfully. Inference produces bounding boxes and damage predictions.
- **`not_configured`**: `MODEL_PATH` is empty or the model file does not exist. The server starts normally, returns `model_status: "not_configured"`, empty detections `[]`, and helpful setup instructions. **No fake predictions are ever generated.**
- **`failed_to_load`**: Model file exists but failed to initialize. Handled gracefully with explicit diagnostic warnings.

---

## API Endpoint Reference

| Method | Endpoint | Auth* | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | – | API status, version, and model status |
| `GET` | `/health` | – | Health check (DB & model status) |
| `GET` | `/statistics` | – | Aggregate report statistics |
| `GET` | `/analytics` | – | Analytics data + reports-over-time series |
| `GET` | `/reports` | – | List reports (filters: `status`, `damage_type`, `severity`, `priority_level`, `has_location`, `limit`, `offset`) |
| `GET` | `/reports/map` | – | Geotagged reports only (for the GIS view) |
| `GET` | `/reports/{id}` | – | Get a single report |
| `POST` | `/analyze-image` | ✔ | Upload a road image for detection & severity/priority analysis |
| `POST` | `/reports` | ✔ | Create a report (JSON) |
| `POST` | `/reports/upload` | ✔ | Create a report with optional image upload (multipart) |
| `PATCH` | `/reports/{id}` | ✔ | Update report fields (e.g. status) |
| `DELETE` | `/reports/{id}` | ✔ | Delete a report and its stored images |

\* **Auth** = guarded by the optional API key (see [Security](#security)). When `API_KEY` is unset (the local default) these endpoints are open.
Static assets: `/app` serves the SPA `index.html`, and `/uploads/*` serves stored images.

### `POST /analyze-image` Details

- **Accepted formats**: `JPG`, `JPEG`, `PNG`, `WEBP` (max 10 MB). Content type, extension, size, and Pillow readability are all validated.
- **Request**: `multipart/form-data` with a `file` field.
- **Response**:
```json
{
  "success": true,
  "model_status": "available",
  "is_model_active": true,
  "detections": [
    {
      "damage_type": "POTHOLE",
      "raw_class_name": "pothole",
      "confidence": 0.91,
      "bounding_box": {"x1": 120.0, "y1": 150.0, "x2": 450.0, "y2": 380.0},
      "severity": "HIGH",
      "severity_reason": "High severity: Critical pothole occupying 12.5% of image frame.",
      "area_ratio": 0.125
    }
  ],
  "overall_severity": "HIGH",
  "priority_score": 83.0,
  "priority_level": "HIGH",
  "priority_reason": "High priority score (83.0/100) calculated based on ...",
  "annotated_image": "uploads/annotated_a1b2c3d4.jpg",
  "original_image": "uploads/damage_e5f6g7h8.jpg",
  "warnings": []
}
```
> In **no-model mode** the same shape is returned with `is_model_active: false`, `detections: []`, and a `warnings` entry explaining how to configure a model.
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
> Optional: to run a *real* road-damage model, also install the AI extras
> (`pip install -r requirements-ai.txt`) and place your weights in `models/`.
> Without them the app runs safely in no-model mode and never fabricates results.

### 3. Configure `.env`
```bash
cp .env.example .env
```

### 4. Start FastAPI Server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### 5. Open Frontend UI
- FastAPI serves the SPA at `http://localhost:8000/app`.
- Or double-click `frontend/index.html` (the API base auto-resolves to `http://localhost:8000`).

---

## Environment Variables

All variables are optional; sensible local defaults apply. Copy `.env.example` to `.env`.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Bind host (informational; Render provides `$PORT`). |
| `FRONTEND_ORIGIN` | localhost origins | Comma-separated CORS origins. Set your deployed frontend origin in production. |
| `DATABASE_URL` | `sqlite:///./road_damage.db` | SQLAlchemy database URL. Production with a disk: `sqlite:////data/road_damage.db`; or a Postgres URL. |
| `UPLOADS_DIR` | `backend/uploads` | Where uploaded/annotated images are stored. Production with a disk: `/data/uploads`. |
| `MODEL_PATH` | *(empty)* | Path to YOLO `.pt` / ONNX model. Empty ⇒ no-model mode. |
| `CONFIDENCE_THRESHOLD` | `0.5` | Minimum detection confidence. The bundled `models/best.pt` ships with `0.25` in `.env` (see note above). |
| `API_KEY` | *(empty)* | If set, `POST`/`PATCH`/`DELETE` require header `X-API-Key`. Empty ⇒ writes open (local default). |

> `PORT` is provided by the Render runtime and must not be overridden.

---

## Running the Tests

```bash
cd backend
python -m pytest
```
The suite in `backend/tests/` starts a real Uvicorn server in a subprocess and drives it over HTTP using only the standard library (no `httpx` required). It covers health, statistics, report CRUD, validation errors, the image-analysis endpoint (no-model mode + invalid input), and API-key protection.

> **Hermetic by default**: `conftest.py` forces `MODEL_PATH=""` for the default fixtures, so the tests always run in **no-model mode** regardless of any model you configured in your local `.env`. This keeps startup fast and the no-model assertions (`model_status: "not_configured"`, empty detections) deterministic.
>
> **Model-mode tests** (`tests/test_model_mode.py`) additionally exercise the real inference path. They run only when weights exist at `models/best.pt` **and** Ultralytics is installed; otherwise they are automatically **skipped**, so the suite stays green on any machine.

---

## AI / Model Setup

1. Install the optional CV dependencies: `pip install -r backend/requirements-ai.txt`.
2. Place your weights in `models/` (e.g. `models/yolov8_road_damage.pt`).
3. Set `MODEL_PATH=models/yolov8_road_damage.pt` in `.env`.

### No-Model / Demo Behaviour
If `MODEL_PATH` is unset or the file is missing, the server still starts and every endpoint works. `/analyze-image` returns `model_status: "not_configured"`, `is_model_active: false`, empty `detections: []`, and setup instructions in `warnings`. **The application never fabricates detections.** Upload, storage, mapping, and reporting all remain fully usable — you can still save a report manually or from an upload.

### Model Status Values
- `available` — model loaded; real inference runs (`is_model_active: true`).
- `not_configured` — no model path / file; safe empty response.
- `failed_to_load` — model present but failed to initialise; diagnostic warnings returned.

---

## Deployment

### Backend on Render
`render.yaml` defines a Python web service (`rootDir: backend`) that installs `requirements.txt` and starts Gunicorn with a Uvicorn worker (`--bind 0.0.0.0:$PORT`).

- **Persistent storage**: SQLite plus the `/data` disk requires a paid instance type; the blueprint uses `plan: starter`. Free instances do **not** support disks — for the free tier remove the `disk:` block and use a managed Postgres `DATABASE_URL` (comments in `render.yaml` show how).
- **Environment**: set `FRONTEND_ORIGIN` to your deployed frontend origin and set `API_KEY` as a Render **secret**. `render.yaml` uses clearly-labelled placeholders and never contains real secrets.
- **Uploads**: `UPLOADS_DIR=/data/uploads` keeps images on the same persistent disk as the database so they survive redeploys.

### Frontend
- **Served by the backend (simplest)**: deploy only the backend and open `https://<your-backend>/app`. Same-origin — no extra configuration.
- **Separate host (e.g. Vercel/Netlify)**: deploy the `frontend/` directory and set the backend URL in `frontend/index.html`'s `<meta name="api-base-url" content="https://<your-backend>.onrender.com">`, then add that frontend origin to the backend's `FRONTEND_ORIGIN` so CORS allows it. Do not hard-code secrets; the backend URL is a public endpoint.

---

## Storage & Database Considerations
- Default database is SQLite at `backend/road_damage.db` (git-ignored). `migrate_db()` adds newly-introduced columns on startup.
- Uploaded and annotated images live in `UPLOADS_DIR` (default `backend/uploads/`, git-ignored).
- On an ephemeral filesystem (e.g. Render free tier) images and SQLite do not survive redeploys — use a persistent disk or managed database/object storage in production.

---

## Security
- **Write protection**: set `API_KEY` to require `X-API-Key` on all mutating endpoints. The SPA can send it via `<meta name="api-key">`. That value is visible in page source, so it is lightweight abuse protection, not a strong secret.
- **Upload safety**: extension, content type, size (≤10 MB), and Pillow readability are validated; files are stored under random UUID names to prevent path traversal or overwrite.
- **CORS**: `FRONTEND_ORIGIN` whitelists production origins, while a narrowly scoped regex permits any `localhost`/`127.0.0.1` port for local development. Wildcards are never combined with credentials.
- **Errors**: API errors return concise JSON `detail` messages; internal stack traces are not exposed to clients.

---

## Notes & Limitations
- Severity and priority scores are AI-assisted heuristics for triage; they do **not** replace certified civil-engineering inspection.
- Real detection requires you to supply model weights; none are bundled (to avoid shipping large binaries).
- GIS map tiles are loaded from OpenStreetMap and require internet access in the browser.
