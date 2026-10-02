import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Text
from database import Base


class DamageType(str, enum.Enum):
    POTHOLE = "POTHOLE"
    LONGITUDINAL_CRACK = "LONGITUDINAL_CRACK"
    TRANSVERSE_CRACK = "TRANSVERSE_CRACK"
    ALLIGATOR_CRACK = "ALLIGATOR_CRACK"
    OTHER = "OTHER"
    NO_DAMAGE = "NO_DAMAGE"


class SeverityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReportStatus(str, enum.Enum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    RESOLVED = "RESOLVED"


class RoadDamageReport(Base):
    __tablename__ = "road_damage_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    image_path = Column(String(500), nullable=True)
    annotated_image_path = Column(String(500), nullable=True)
    damage_type = Column(Enum(DamageType), nullable=True)
    severity = Column(Enum(SeverityLevel), nullable=True)
    confidence = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.NEW, nullable=False)
    description = Column(Text, nullable=True)
    priority_score = Column(Float, nullable=True)
    priority_level = Column(String(20), nullable=True)
    priority_reason = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "image_path": self.image_path,
            "annotated_image_path": self.annotated_image_path,
            "damage_type": self.damage_type.value if self.damage_type else None,
            "severity": self.severity.value if self.severity else None,
            "confidence": self.confidence,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "status": self.status.value if self.status else None,
            "description": self.description,
            "priority_score": self.priority_score,
            "priority_level": self.priority_level,
            "priority_reason": self.priority_reason,    
        }