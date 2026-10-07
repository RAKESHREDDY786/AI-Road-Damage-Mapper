from typing import Dict, Any, List
from .. import models


def calculate_severity(
    damage_type: str,
    confidence: float,
    bbox: Dict[str, float],
    image_width: int,
    image_height: int,
) -> Dict[str, Any]:
    """Calculates AI-assisted severity score (LOW, MEDIUM, HIGH) for a single detection based on damage classification and relative surface area coverage.
    
    Note: This is an AI-assisted heuristic estimation and does not constitute a certified structural engineering assessment.
    """
    if damage_type == models.DamageType.NO_DAMAGE.value:
        return {"level": models.SeverityLevel.LOW.value, "reason": "No structural distress detected."}

    # Compute bounding box area relative to total image area
    bbox_width = max(0, bbox.get("x2", 0) - bbox.get("x1", 0))
    bbox_height = max(0, bbox.get("y2", 0) - bbox.get("y1", 0))
    bbox_area = bbox_width * bbox_height

    total_image_area = max(1, image_width * image_height)
    area_ratio = bbox_area / total_image_area

    # Base severity score derived from damage type vulnerability
    base_scores = {
        models.DamageType.POTHOLE.value: 3,
        models.DamageType.ALLIGATOR_CRACK.value: 3,
        models.DamageType.LONGITUDINAL_CRACK.value: 2,
        models.DamageType.TRANSVERSE_CRACK.value: 2,
        models.DamageType.OTHER.value: 1,
    }
    score = base_scores.get(damage_type, 1)

    # Size-based severity escalation
    if area_ratio >= 0.08:  # Takes up > 8% of the image frame
        score += 2
    elif area_ratio >= 0.025:  # Takes up > 2.5% of the frame
        score += 1

    # High confidence boost
    if confidence >= 0.85:
        score += 0.5

    # Determine final level
    if score >= 4.5:
        level = models.SeverityLevel.HIGH.value
        reason = f"High severity: Critical {damage_type.lower().replace('_', ' ')} occupying {area_ratio*100:.1f}% of image frame."
    elif score >= 2.5:
        level = models.SeverityLevel.MEDIUM.value
        reason = f"Medium severity: Moderate {damage_type.lower().replace('_', ' ')} occupying {area_ratio*100:.1f}% of image frame."
    else:
        level = models.SeverityLevel.LOW.value
        reason = f"Low severity: Minor {damage_type.lower().replace('_', ' ')} distress."

    return {
        "level": level,
        "reason": reason,
        "area_ratio": round(area_ratio, 4),
    }


def calculate_overall_severity(detections: List[Dict[str, Any]]) -> str:
    """Computes overall aggregate road severity from list of individual detections."""
    if not detections:
        return models.SeverityLevel.LOW.value

    severities = [d.get("severity") for d in detections]
    if models.SeverityLevel.HIGH.value in severities or len(detections) >= 3:
        return models.SeverityLevel.HIGH.value
    if models.SeverityLevel.MEDIUM.value in severities or len(detections) >= 2:
        return models.SeverityLevel.MEDIUM.value

    return models.SeverityLevel.LOW.value
