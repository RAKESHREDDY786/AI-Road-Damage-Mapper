import os
import uuid
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from PIL import Image

from . import models
from . import schemas
from .database import engine, get_db, migrate_db
from .services.detection_service import detection_service
from .services.priority_service import calculate_priority

# Load environment variables
load_dotenv()

# Ensure database tables exist & apply migrations
models.Base.metadata.create_all(bind=engine)
migrate_db()

app = FastAPI(
    title="AI Road Damage Mapper API",
    description="Backend REST API with Computer Vision detection, validation, database ORM, and report management.",
    version="2.0.0",
)

# Upload directory setup
# Configurable so uploads can live on a persistent volume in production
# (e.g. UPLOADS_DIR=/data/uploads on Render). Defaults to backend/uploads/.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

_uploads_env = os.getenv("UPLOADS_DIR", "").strip()
UPLOADS_DIR = os.path.abspath(_uploads_env) if _uploads_env else DEFAULT_UPLOADS_DIR
os.makedirs(UPLOADS_DIR, exist_ok=True)

FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# Configure CORS
raw_origins = os.getenv(
    "FRONTEND_ORIGIN",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:5500",
)
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

# Allow any local development origin (Live Server / Vite / CRA on arbitrary ports).
# This regex intentionally matches ONLY localhost/127.0.0.1 so it is safe in production.
LOCAL_DEV_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=LOCAL_DEV_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploaded files directory
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# ─── Optional API-key protection for mutating endpoints ───────────────────────
# Set API_KEY in the environment (Render dashboard) to require the header
# `X-API-Key: <value>` on POST/PATCH/DELETE requests. If API_KEY is empty
# (the local-development default) no key is required. Secrets are never hard-coded.
API_KEY = os.getenv("API_KEY", "").strip()


def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Dependency that enforces the API key for data-changing endpoints when configured."""
    if not API_KEY:
        return  # protection disabled (e.g. local development)
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "X-API-Key"},
        )


# File Upload Security & Validation
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit


def validate_and_save_image(file: UploadFile) -> str:
    """Validates uploaded image file type, size, readability, and saves safely with UUID filename."""
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded or filename missing."
        )

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed formats: .jpg, .jpeg, .png, .webp.",
        )

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type '{file.content_type}'. Allowed types: JPG, JPEG, PNG, WEBP.",
        )

    # Read binary content to verify size & valid image binary structure
    try:
        contents = file.file.read()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to read uploaded file contents."
        )
    finally:
        file.file.seek(0)

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds maximum 10MB limit."
        )

    # Validate image readability using Pillow
    try:
        image = Image.open(file.file)
        image.verify()
        file.file.seek(0)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is corrupted or not a valid image."
        )

    # Generate safe unique filename to prevent path traversal
    unique_filename = f"damage_{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(UPLOADS_DIR, unique_filename)

    with open(saved_path, "wb") as f:
        f.write(contents)

    return f"uploads/{unique_filename}"


def get_upload_file_path(relative_path: str) -> str:
    return os.path.join(UPLOADS_DIR, os.path.basename(relative_path))


# Base API Routes
@app.get("/", tags=["System"])
def read_root():
    return {
        "project": "AI Road Damage Mapper",
        "version": "2.0.0",
        "status": "online",
        "model_status": detection_service.model_status,
        "documentation": "/docs",
    }


@app.get("/health", response_model=schemas.HealthCheckResponse, tags=["System"])
def health_check(db: Session = Depends(get_db)):
    db_status = "connected"
    try:
        db.execute(models.Base.metadata.tables["road_damage_reports"].select().limit(1))
    except Exception:
        db_status = "disconnected"

    return schemas.HealthCheckResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
        timestamp=datetime.utcnow(),
        model_status=detection_service.model_status,
        version="2.0.0",
    )


# AI Image Analysis Endpoint
@app.post(
    "/analyze-image",
    response_model=schemas.ImageAnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["AI Analysis"],
    dependencies=[Depends(require_api_key)],
)
def analyze_image(file: UploadFile = File(...)):
    """Accepts an uploaded road image, validates file safety, and runs computer vision inference.
    
    Returns structured bounding box detections, confidence scores, severity level, priority estimate, and annotated image path.
    Does NOT fabricate results if no model is configured or if no damage is detected.
    """
    saved_relative_path = validate_and_save_image(file)
    full_image_path = get_upload_file_path(saved_relative_path)

    # Run computer vision detection service
    analysis_result, annotated_relative_path = detection_service.analyze_image(
        image_path=full_image_path, uploads_dir=UPLOADS_DIR
    )

    # Calculate initial priority score estimate
    detections = analysis_result.get("detections", [])
    top_damage_type = detections[0].get("damage_type") if detections else models.DamageType.NO_DAMAGE.value
    top_conf = max([d.get("confidence", 0.0) for d in detections], default=0.0)
    top_area = max([d.get("area_ratio", 0.0) if "area_ratio" in d else 0.0 for d in detections], default=0.0)

    p_res = calculate_priority(
        severity=analysis_result.get("overall_severity"),
        damage_type=top_damage_type,
        confidence=top_conf,
        area_ratio=top_area,
        detections_count=len(detections),
    )

    analysis_result["original_image"] = saved_relative_path
    analysis_result["priority_score"] = p_res["priority_score"]
    analysis_result["priority_level"] = p_res["priority_level"]
    analysis_result["priority_reason"] = p_res["priority_reason"]

    return analysis_result


# Report Management API
@app.post(
    "/reports",
    response_model=schemas.ReportResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reports"],
    dependencies=[Depends(require_api_key)],
)
def create_report(report_data: schemas.ReportCreate, db: Session = Depends(get_db)):
    """Create a new road damage report from JSON payload."""
    if report_data.latitude is not None and (report_data.latitude < -90 or report_data.latitude > 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90.")
    if report_data.longitude is not None and (report_data.longitude < -180 or report_data.longitude > 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180.")

    # Calculate or refine priority if missing
    p_score = report_data.priority_score
    p_level = report_data.priority_level
    p_reason = report_data.priority_reason

    if p_score is None or p_level is None:
        p_res = calculate_priority(
            severity=report_data.severity,
            damage_type=report_data.damage_type,
            confidence=report_data.confidence,
            latitude=report_data.latitude,
            longitude=report_data.longitude,
        )
        p_score = p_res["priority_score"]
        p_level = p_res["priority_level"]
        p_reason = p_res["priority_reason"]

    db_report = models.RoadDamageReport(
        image_path=report_data.image_path,
        annotated_image_path=report_data.annotated_image_path,
        damage_type=report_data.damage_type,
        severity=report_data.severity,
        confidence=report_data.confidence,
        latitude=report_data.latitude,
        longitude=report_data.longitude,
        status=report_data.status,
        description=report_data.description,
        priority_score=p_score,
        priority_level=p_level,
        priority_reason=p_reason,
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


@app.post(
    "/reports/upload",
    response_model=schemas.ReportResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reports"],
    dependencies=[Depends(require_api_key)],
)
def create_report_with_upload(
    file: Optional[UploadFile] = File(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    damage_type: Optional[models.DamageType] = Form(None),
    severity: Optional[models.SeverityLevel] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new road damage report with optional image file upload."""
    if latitude is not None and (latitude < -90 or latitude > 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90.")
    if longitude is not None and (longitude < -180 or longitude > 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180.")

    image_path = None
    if file and file.filename:
        image_path = validate_and_save_image(file)

    p_res = calculate_priority(
        severity=severity,
        damage_type=damage_type,
        latitude=latitude,
        longitude=longitude,
    )

    db_report = models.RoadDamageReport(
        image_path=image_path,
        damage_type=damage_type,
        severity=severity,
        latitude=latitude,
        longitude=longitude,
        description=description,
        status=models.ReportStatus.NEW,
        priority_score=p_res["priority_score"],
        priority_level=p_res["priority_level"],
        priority_reason=p_res["priority_reason"],
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


@app.get("/reports", response_model=List[schemas.ReportResponse], tags=["Reports"])
def get_reports(
    status: Optional[models.ReportStatus] = Query(None, description="Filter by status"),
    damage_type: Optional[models.DamageType] = Query(None, description="Filter by damage type"),
    severity: Optional[models.SeverityLevel] = Query(None, description="Filter by severity level"),
    priority_level: Optional[str] = Query(None, description="Filter by priority level (LOW, MEDIUM, HIGH)"),
    has_location: Optional[bool] = Query(None, description="Filter reports that have GPS coordinates"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve list of road damage reports with optional filters."""
    query = db.query(models.RoadDamageReport)

    if status:
        query = query.filter(models.RoadDamageReport.status == status)
    if damage_type:
        query = query.filter(models.RoadDamageReport.damage_type == damage_type)
    if severity:
        query = query.filter(models.RoadDamageReport.severity == severity)
    if priority_level:
        query = query.filter(models.RoadDamageReport.priority_level == priority_level.upper())
    if has_location is True:
        query = query.filter(
            models.RoadDamageReport.latitude.isnot(None), models.RoadDamageReport.longitude.isnot(None)
        )
    elif has_location is False:
        query = query.filter(
            (models.RoadDamageReport.latitude.is_(None)) | (models.RoadDamageReport.longitude.is_(None))
        )

    reports = query.order_by(models.RoadDamageReport.timestamp.desc()).offset(offset).limit(limit).all()
    return reports


@app.get("/reports/map", response_model=List[schemas.ReportResponse], tags=["GIS Map"])
def get_map_reports(db: Session = Depends(get_db)):
    """Returns only geotagged reports with valid latitude and longitude for interactive map rendering."""
    return (
        db.query(models.RoadDamageReport)
        .filter(
            models.RoadDamageReport.latitude.isnot(None),
            models.RoadDamageReport.longitude.isnot(None),
        )
        .order_by(models.RoadDamageReport.timestamp.desc())
        .all()
    )


@app.get("/reports/{report_id}", response_model=schemas.ReportResponse, tags=["Reports"])
def get_report(report_id: int, db: Session = Depends(get_db)):
    """Retrieve a single report by ID."""
    report = db.query(models.RoadDamageReport).filter(models.RoadDamageReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report with ID {report_id} not found."
        )
    return report


@app.patch("/reports/{report_id}", response_model=schemas.ReportResponse, tags=["Reports"], dependencies=[Depends(require_api_key)])
def update_report(
    report_id: int, report_update: schemas.ReportUpdate, db: Session = Depends(get_db)
):
    """Update attributes of an existing report."""
    report = db.query(models.RoadDamageReport).filter(models.RoadDamageReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report with ID {report_id} not found."
        )

    update_data = report_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)

    priority_inputs = {"severity", "damage_type", "confidence", "latitude", "longitude"}
    if priority_inputs.intersection(update_data):
        p_res = calculate_priority(
            severity=report.severity,
            damage_type=report.damage_type,
            confidence=report.confidence,
            latitude=report.latitude,
            longitude=report.longitude,
        )
        report.priority_score = p_res["priority_score"]
        report.priority_level = p_res["priority_level"]
        report.priority_reason = p_res["priority_reason"]

    db.commit()
    db.refresh(report)
    return report


@app.delete("/reports/{report_id}", status_code=status.HTTP_200_OK, tags=["Reports"], dependencies=[Depends(require_api_key)])
def delete_report(report_id: int, db: Session = Depends(get_db)):
    """Delete a report from database and clean up associated stored image file."""
    report = db.query(models.RoadDamageReport).filter(models.RoadDamageReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report with ID {report_id} not found."
        )

    # Delete physical image files if present
    for path_attr in [report.image_path, report.annotated_image_path]:
        if path_attr:
            full_path = get_upload_file_path(path_attr)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass

    db.delete(report)
    db.commit()
    return {"message": f"Report {report_id} deleted successfully.", "id": report_id}


@app.get("/statistics", response_model=schemas.StatisticsResponse, tags=["Analytics"])
def get_statistics(db: Session = Depends(get_db)):
    """Return database statistics for road damage reports. Returns empty/zero values if no reports exist."""
    total_reports = db.query(models.RoadDamageReport).count()

    by_damage_type = {dt.value: 0 for dt in models.DamageType}
    by_severity = {sev.value: 0 for sev in models.SeverityLevel}
    by_status = {st.value: 0 for st in models.ReportStatus}
    by_priority = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    high_priority_count = 0
    open_count = 0
    reviewed_count = 0
    resolved_count = 0

    if total_reports > 0:
        dt_counts = db.query(models.RoadDamageReport.damage_type, func.count(models.RoadDamageReport.id)).group_by(models.RoadDamageReport.damage_type).all()
        for dt, count in dt_counts:
            if dt is not None:
                key = dt.value if hasattr(dt, 'value') else str(dt)
                by_damage_type[key] = count

        sev_counts = db.query(models.RoadDamageReport.severity, func.count(models.RoadDamageReport.id)).group_by(models.RoadDamageReport.severity).all()
        for sev, count in sev_counts:
            if sev is not None:
                key = sev.value if hasattr(sev, 'value') else str(sev)
                by_severity[key] = count

        st_counts = db.query(models.RoadDamageReport.status, func.count(models.RoadDamageReport.id)).group_by(models.RoadDamageReport.status).all()
        for st, count in st_counts:
            if st is not None:
                key = st.value if hasattr(st, 'value') else str(st)
                by_status[key] = count
                if key == models.ReportStatus.NEW.value:
                    open_count = count
                elif key == models.ReportStatus.REVIEWED.value:
                    reviewed_count = count
                elif key == models.ReportStatus.RESOLVED.value:
                    resolved_count = count

        p_counts = db.query(models.RoadDamageReport.priority_level, func.count(models.RoadDamageReport.id)).group_by(models.RoadDamageReport.priority_level).all()
        for plevel, count in p_counts:
            if plevel:
                by_priority[plevel.upper()] = count
                if plevel.upper() == "HIGH":
                    high_priority_count = count

        avg_priority = db.query(func.avg(models.RoadDamageReport.priority_score)).filter(models.RoadDamageReport.priority_score.isnot(None)).scalar()
        avg_priority_val = round(float(avg_priority), 2) if avg_priority is not None else 0.0
    else:
        avg_priority_val = 0.0

    return schemas.StatisticsResponse(
        total_reports=total_reports,
        by_damage_type=by_damage_type,
        by_severity=by_severity,
        by_status=by_status,
        by_priority_level=by_priority,
        average_priority_score=avg_priority_val,
        high_priority_count=high_priority_count,
        open_reports_count=open_count,
        reviewed_reports_count=reviewed_count,
        resolved_reports_count=resolved_count,
    )


@app.get("/analytics", response_model=schemas.AnalyticsResponse, tags=["Analytics"])
def get_analytics(db: Session = Depends(get_db)):
    """Returns real database analytics data for chart visualizations."""
    stats = get_statistics(db)

    # Time series grouping by day
    time_series = []
    if stats.total_reports > 0:
        daily_counts = (
            db.query(
                func.date(models.RoadDamageReport.timestamp).label("report_date"),
                func.count(models.RoadDamageReport.id),
            )
            .group_by("report_date")
            .order_by("report_date")
            .all()
        )
        for date_val, count in daily_counts:
            if date_val:
                time_series.append({"date": str(date_val), "count": count})

    return schemas.AnalyticsResponse(
        total_reports=stats.total_reports,
        high_priority_count=stats.high_priority_count,
        open_reports_count=stats.open_reports_count,
        reviewed_reports_count=stats.reviewed_reports_count,
        resolved_reports_count=stats.resolved_reports_count,
        average_priority_score=stats.average_priority_score,
        by_damage_type=stats.by_damage_type,
        by_severity=stats.by_severity,
        by_status=stats.by_status,
        by_priority_level=stats.by_priority_level,
        reports_over_time=time_series,
        has_data=stats.total_reports > 0,
    )


# Serve frontend static assets
if os.path.exists(FRONTEND_DIR):
    @app.get("/app", include_in_schema=False)
    def serve_frontend_app():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
