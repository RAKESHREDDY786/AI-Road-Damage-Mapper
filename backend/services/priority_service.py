"""
AI Road Damage Mapper - Maintenance Priority Engine Service
Calculates transparent, deterministic maintenance-priority scores and categories (LOW, MEDIUM, HIGH)
based on damage severity, vulnerability, confidence, damage area, and location availability.

DISCLAIMER: AI-assisted maintenance priority estimate. Results are for decision support and do not replace certified civil engineering inspection.
"""

from typing import Dict, Any, Optional
import models


DISCLAIMER_TEXT = (
    "AI-assisted maintenance priority estimate. "
    "Results are for decision support and do not replace certified civil engineering inspection."
)


def calculate_priority(
    severity: Optional[str] = None,
    damage_type: Optional[str] = None,
    confidence: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    area_ratio: float = 0.0,
    detections_count: int = 1,
) -> Dict[str, Any]:
    """Calculates a deterministic AI-assisted maintenance priority score (0.0 to 100.0)

    and returns priority category (LOW, MEDIUM, HIGH), rationale explanation, and disclaimer.
    """
    # 1. Base Score derived from Severity (Max: 45 points)
    severity_str = (severity.value if hasattr(severity, "value") else str(severity or "")).upper()
    if severity_str == models.SeverityLevel.HIGH.value:
        base_severity_score = 45.0
    elif severity_str == models.SeverityLevel.MEDIUM.value:
        base_severity_score = 25.0
    elif severity_str == models.SeverityLevel.LOW.value:
        base_severity_score = 10.0
    else:
        base_severity_score = 15.0

    # 2. Base Score derived from Damage Type Vulnerability (Max: 20 points)
    dt_str = (damage_type.value if hasattr(damage_type, "value") else str(damage_type or "")).upper()
    if dt_str == models.DamageType.POTHOLE.value:
        type_score = 20.0
    elif dt_str == models.DamageType.ALLIGATOR_CRACK.value:
        type_score = 18.0
    elif dt_str in [models.DamageType.LONGITUDINAL_CRACK.value, models.DamageType.TRANSVERSE_CRACK.value]:
        type_score = 12.0
    elif dt_str == models.DamageType.OTHER.value:
        type_score = 5.0
    elif dt_str == models.DamageType.NO_DAMAGE.value:
        type_score = 0.0
    else:
        type_score = 8.0

    # 3. Confidence Factor (Max: 10 points)
    conf_val = float(confidence) if confidence is not None else 0.8
    conf_score = max(0.0, min(1.0, conf_val)) * 10.0

    # 4. Damage Occupancy & Multi-Detection Density Factor (Max: 15 points)
    density_score = 0.0
    if area_ratio >= 0.08:
        density_score += 10.0
    elif area_ratio >= 0.02:
        density_score += 5.0

    if detections_count >= 3:
        density_score += 5.0
    elif detections_count >= 2:
        density_score += 2.5

    density_score = min(15.0, density_score)

    # 5. Geolocation Actionability Factor (Max: 10 points)
    # Having verified GPS coordinates allows dispatch of maintenance repair crews
    location_available = latitude is not None and longitude is not None
    location_score = 10.0 if location_available else 0.0

    # Calculate Total Score (0 - 100)
    total_score = round(
        min(100.0, max(0.0, base_severity_score + type_score + conf_score + density_score + location_score)), 1
    )

    # Determine Priority Category
    if total_score >= 60.0:
        priority_level = "HIGH"
    elif total_score >= 35.0:
        priority_level = "MEDIUM"
    else:
        priority_level = "LOW"

    # Construct Rationale Explanation
    formatted_type = dt_str.lower().replace("_", " ") if dt_str else "road damage"
    reasons = []
    if severity_str:
        reasons.append(f"{severity_str.lower()} severity")
    reasons.append(f"{formatted_type}")
    if confidence is not None:
        reasons.append(f"{confidence*100:.0f}% confidence")
    if location_available:
        reasons.append("GPS location available")
    else:
        reasons.append("no GPS location supplied")

    reason_str = f"{priority_level.capitalize()} priority score ({total_score}/100) calculated based on " + ", ".join(reasons) + "."

    return {
        "priority_score": total_score,
        "priority_level": priority_level,
        "priority_reason": reason_str,
        "disclaimer": DISCLAIMER_TEXT,
    }
