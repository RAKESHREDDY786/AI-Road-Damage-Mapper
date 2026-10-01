from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, ConfigDict
from models import DamageType, SeverityLevel, ReportStatus


class ReportBase(BaseModel):
    image_path: Optional[str] = Field(None, description="Relative path to stored original image file")
    annotated_image_path: Optional[str] = Field(None, description="Relative path to stored annotated image file")
    damage_type: Optional[DamageType] = Field(None, description="Categorized road damage type")
    severity: Optional[SeverityLevel] = Field(None, description="Assessed severity level")
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="AI detection confidence score between 0.0 and 1.0"
    )
    latitude: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Geographic latitude coordinate (-90 to 90)"
    )
    longitude: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Geographic longitude coordinate (-180 to 180)"
    )
    status: ReportStatus = Field(default=ReportStatus.NEW, description="Workflow status of report")
    description: Optional[str] = Field(None, description="Optional text description or inspector notes")
    priority_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Calculated maintenance priority score (0.0 to 100.0)"
    )
    priority_level: Optional[str] = Field(None, description="Priority category (LOW, MEDIUM, HIGH)")
    priority_reason: Optional[str] = Field(None, description="AI-assisted priority score rationale explanation")


class ReportCreate(ReportBase):
    pass


class ReportUpdate(BaseModel):
    image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    damage_type: Optional[DamageType] = None
    severity: Optional[SeverityLevel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    status: Optional[ReportStatus] = None
    description: Optional[str] = None
    priority_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    priority_level: Optional[str] = None
    priority_reason: Optional[str] = None


class ReportResponse(ReportBase):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class StatisticsResponse(BaseModel):
    total_reports: int
    by_damage_type: Dict[str, int]
    by_severity: Dict[str, int]
    by_status: Dict[str, int]
    by_priority_level: Dict[str, int] = {}
    average_priority_score: float
    high_priority_count: int = 0
    open_reports_count: int = 0
    reviewed_reports_count: int = 0
    resolved_reports_count: int = 0


class AnalyticsResponse(BaseModel):
    total_reports: int
    high_priority_count: int
    open_reports_count: int
    reviewed_reports_count: int
    resolved_reports_count: int
    average_priority_score: float
    by_damage_type: Dict[str, int]
    by_severity: Dict[str, int]
    by_status: Dict[str, int]
    by_priority_level: Dict[str, int]
    reports_over_time: List[Dict[str, Any]]
    has_data: bool


class HealthCheckResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
    model_status: str
    version: str = "2.0.0"


# Stage 2 & 3 AI Computer Vision Analysis Schemas
class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class DetectionItem(BaseModel):
    damage_type: str
    raw_class_name: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    bounding_box: BoundingBox
    severity: str
    severity_reason: Optional[str] = None


class ImageAnalysisResponse(BaseModel):
    success: bool
    model_status: str
    detections: List[DetectionItem]
    overall_severity: str
    priority_score: Optional[float] = None
    priority_level: Optional[str] = None
    priority_reason: Optional[str] = None
    annotated_image: Optional[str] = None
    original_image: Optional[str] = None
    warnings: List[str] = []


class SaveAnalysisToReportRequest(BaseModel):
    image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    damage_type: Optional[DamageType] = None
    severity: Optional[SeverityLevel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    description: Optional[str] = None
    priority_score: Optional[float] = None
    priority_level: Optional[str] = None
    priority_reason: Optional[str] = None

