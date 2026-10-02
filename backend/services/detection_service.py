import os
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

import models
from services.severity_service import calculate_severity, calculate_overall_severity

load_dotenv()

logger = logging.getLogger("detection_service")

# Class mapping mechanism: maps model raw class strings or IDs to conceptual application damage types
DEFAULT_CLASS_MAPPING: Dict[str, str] = {
    # Numerical ID string mappings (common in YOLO RDD2020 / RDD2022 models)
    "0": models.DamageType.POTHOLE.value,
    "1": models.DamageType.LONGITUDINAL_CRACK.value,
    "2": models.DamageType.TRANSVERSE_CRACK.value,
    "3": models.DamageType.ALLIGATOR_CRACK.value,
    "4": models.DamageType.OTHER.value,
    
    # Textual class label mappings
    "pothole": models.DamageType.POTHOLE.value,
    "longitudinal crack": models.DamageType.LONGITUDINAL_CRACK.value,
    "longitudinal_crack": models.DamageType.LONGITUDINAL_CRACK.value,
    "transverse crack": models.DamageType.TRANSVERSE_CRACK.value,
    "transverse_crack": models.DamageType.TRANSVERSE_CRACK.value,
    "alligator crack": models.DamageType.ALLIGATOR_CRACK.value,
    "alligator_crack": models.DamageType.ALLIGATOR_CRACK.value,
    "crack": models.DamageType.LONGITUDINAL_CRACK.value,
    "rutting": models.DamageType.OTHER.value,
    "other": models.DamageType.OTHER.value,
    "no_damage": models.DamageType.NO_DAMAGE.value,
}


class DetectionService:
    """Modular Computer Vision Service for Road Damage Detection.
    
    Manages model loading lifecycle, inference execution, bounding box extraction,
    and annotated image generation. Never fabricates detection results.
    """

    def __init__(self):
        self.model_path: str = os.getenv("MODEL_PATH", "").strip()
        
        try:
            self.confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
        except ValueError:
            self.confidence_threshold = 0.5

        self.model = None
        self.model_type: Optional[str] = None
        self.model_status: str = "not_configured"
        self.status_detail: str = "MODEL_NOT_CONFIGURED: MODEL_PATH environment variable is empty or model file was not provided."
        self.class_mapping: Dict[str, str] = DEFAULT_CLASS_MAPPING.copy()

        # Initialize model singleton on startup
        self._load_model()

    def _load_model(self):
        """Attempts to load computer vision model weights once at startup."""
        if not self.model_path:
            self.model_status = "not_configured"
            self.status_detail = "MODEL_NOT_CONFIGURED: No model path specified in MODEL_PATH environment variable."
            logger.info("DetectionService: No model path configured.")
            return

        # Resolve relative path
        abs_model_path = os.path.abspath(self.model_path)
        if not os.path.exists(abs_model_path):
            self.model_status = "not_configured"
            self.status_detail = f"MODEL_NOT_FOUND: Configured model file does not exist at '{self.model_path}'."
            logger.warning(f"DetectionService: Model file not found at {abs_model_path}")
            return

        # Attempt to load using Ultralytics (YOLOv8) if available
        try:
            from ultralytics import YOLO
            logger.info(f"Loading YOLO model from {abs_model_path}...")
            self.model = YOLO(abs_model_path)
            self.model_type = "ultralytics_yolo"
            self.model_status = "available"
            self.status_detail = f"Model loaded successfully from '{self.model_path}' (Ultralytics YOLO)."
            logger.info("DetectionService: Model loaded successfully.")
            return
        except ImportError:
            logger.info("DetectionService: 'ultralytics' package not installed.")
        except Exception as e:
            logger.error(f"DetectionService: Failed to load YOLO model: {e}")
            self.model_status = "failed_to_load"
            self.status_detail = f"MODEL_LOAD_ERROR: Failed to initialize YOLO model: {str(e)}"
            return

        # Fallback: Attempt OpenCV DNN if model is ONNX / PB
        try:
            import cv2
            logger.info(f"Attempting OpenCV DNN load for {abs_model_path}...")
            self.model = cv2.dnn.readNet(abs_model_path)
            self.model_type = "opencv_dnn"
            self.model_status = "available"
            self.status_detail = f"Model loaded successfully from '{self.model_path}' (OpenCV DNN)."
            return
        except Exception as e:
            self.model_status = "failed_to_load"
            self.status_detail = f"MODEL_LOAD_ERROR: Could not load model with ultralytics or OpenCV DNN: {str(e)}"
            logger.error(f"DetectionService: OpenCV DNN load failed: {e}")

    def map_class_name(self, raw_class_name: Any) -> str:
        """Maps raw model output class identifier to conceptual application damage type."""
        key = str(raw_class_name).strip().lower()
        return self.class_mapping.get(key, models.DamageType.OTHER.value)

    def analyze_image(
        self, image_path: str, uploads_dir: str
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Performs computer vision inference on image.
        
        Returns:
            Tuple of (structured_result_dict, annotated_image_relative_path)
        """
        warnings = []

        if self.model_status != "available" or self.model is None:
            warnings.append(self.status_detail)
            warnings.append(
                "To enable automated road damage detection, place a valid YOLO model binary (.pt) in 'models/' and set MODEL_PATH in '.env'."
            )
            return {
                "success": True,
                "model_status": self.model_status,
                "is_model_active": False,
                "detections": [],
                "overall_severity": models.SeverityLevel.LOW.value,
                "annotated_image": None,
                "warnings": warnings,
            }, None

        # Load image for inference
        try:
            pil_img = Image.open(image_path)
            img_width, img_height = pil_img.size
        except Exception as e:
            return {
                "success": False,
                "model_status": self.model_status,
                "is_model_active": False,
                "detections": [],
                "overall_severity": models.SeverityLevel.LOW.value,
                "annotated_image": None,
                "warnings": [f"Failed to load image for AI inference: {str(e)}"],
            }, None

        detections: List[Dict[str, Any]] = []

        # Run inference based on loaded engine
        if self.model_type == "ultralytics_yolo":
            try:
                results = self.model(image_path, conf=self.confidence_threshold)
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        xyxy = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        raw_name = r.names.get(cls_id, str(cls_id)) if hasattr(r, 'names') else str(cls_id)

                        damage_type = self.map_class_name(raw_name)

                        bbox = {
                            "x1": round(xyxy[0], 1),
                            "y1": round(xyxy[1], 1),
                            "x2": round(xyxy[2], 1),
                            "y2": round(xyxy[3], 1),
                        }

                        severity_info = calculate_severity(
                            damage_type=damage_type,
                            confidence=conf,
                            bbox=bbox,
                            image_width=img_width,
                            image_height=img_height,
                        )

                        detections.append({
                            "damage_type": damage_type,
                            "raw_class_name": str(raw_name),
                            "confidence": round(conf, 4),
                            "bounding_box": bbox,
                            "severity": severity_info["level"],
                            "severity_reason": severity_info["reason"],
                            "area_ratio": severity_info.get("area_ratio", 0.0),
                        })
            except Exception as e:
                logger.error(f"Inference error: {e}")
                warnings.append(f"Inference execution error: {str(e)}")

        # Draw bounding boxes and annotate image if detections exist
        annotated_relative_path = None
        if detections:
            annotated_relative_path = self._generate_annotated_image(
                pil_img, detections, uploads_dir
            )

        overall_severity = calculate_overall_severity(detections)

        return {
            "success": True,
            "model_status": self.model_status,
            "is_model_active": True,
            "detections": detections,
            "overall_severity": overall_severity,
            "annotated_image": annotated_relative_path,
            "warnings": warnings,
        }, annotated_relative_path

    def _generate_annotated_image(
        self, pil_img: Image.Image, detections: List[Dict[str, Any]], uploads_dir: str
    ) -> str:
        """Draws bounding boxes and class/confidence labels onto a copy of the original image."""
        annotated = pil_img.copy()
        draw = ImageDraw.Draw(annotated)

        # Color scheme by severity
        colors = {
            models.SeverityLevel.HIGH.value: "#ef4444",    # Bright Red
            models.SeverityLevel.MEDIUM.value: "#f59e0b",  # Amber Yellow
            models.SeverityLevel.LOW.value: "#10b981",     # Emerald Green
        }

        for det in detections:
            bbox = det["bounding_box"]
            severity = det["severity"]
            damage_type = det["damage_type"]
            conf = det["confidence"]

            color = colors.get(severity, "#3b82f6")

            x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]

            # Draw bounding box outline with thickness 3
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

            # Draw label banner
            label_text = f"{damage_type} ({int(conf * 100)}%)"
            
            # Label background box
            text_bbox = draw.textbbox((x1, max(0, y1 - 20)), label_text)
            draw.rectangle([text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 4, text_bbox[3] + 2], fill=color)
            draw.text((x1, max(0, y1 - 20)), label_text, fill="#ffffff")

        # Save annotated image into uploads directory with unique name
        unique_name = f"annotated_{uuid.uuid4().hex}.jpg"
        save_full_path = os.path.join(uploads_dir, unique_name)
        
        # Convert RGBA to RGB if needed before saving JPEG
        if annotated.mode in ("RGBA", "P"):
            annotated = annotated.convert("RGB")

        annotated.save(save_full_path, "JPEG", quality=90)
        return f"uploads/{unique_name}"


# Singleton instance of DetectionService
detection_service = DetectionService()
