"""Enforcement settings.

Every value has a safe default and can be overridden through an environment
variable (see ``backend/.env.example``).  Values that administrators are
expected to change at runtime (fine amounts, due period) are additionally
stored in MongoDB by :mod:`app.enforcement.fines`; the values here are only the
initial defaults.
"""
import json
import os
from typing import Dict, Tuple

from ..config import _project_path


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> Tuple[str, ...]:
    return tuple(v.strip() for v in os.getenv(name, default).split(",") if v.strip())


def _fines() -> Dict[str, int]:
    defaults = {"red_light": 1000}
    raw = os.getenv("CHALLAN_FINE_AMOUNTS", "").strip()
    if not raw:
        return defaults
    try:
        parsed = {str(k): int(v) for k, v in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError):
        return defaults
    return {**defaults, **parsed}


class EnforcementSettings:
    # Evidence is stored outside the public /results mount and only served
    # through an authenticated endpoint.
    evidence_dir = _project_path(os.getenv("EVIDENCE_DIR", "storage/evidence"))

    # FR10 – red-light detection
    red_light_grace_seconds = _float("RED_LIGHT_GRACE_SECONDS", 0.5)
    sumo_red_light_grace_seconds = _float("SUMO_RED_LIGHT_GRACE_SECONDS", 0.0)
    exempt_vehicle_classes = _csv("VIOLATION_EXEMPT_CLASSES", "Ambulance,Fire Truck")
    duplicate_window_seconds = _float("VIOLATION_DUPLICATE_WINDOW_SECONDS", 2.0)
    video_analyse_fps = _int("VIOLATION_VIDEO_ANALYSE_FPS", 10)
    video_max_frames = _int("VIOLATION_VIDEO_MAX_FRAMES", 3000)
    tracker = os.getenv("VIOLATION_TRACKER", "bytetrack.yaml")

    # FR11 – number-plate recognition
    plate_detector_path = _project_path(
        os.getenv("PLATE_DETECTOR_PATH", "models/anpr/license_plate_yolo11n.pt")
    )
    plate_detector_min_confidence = _float("PLATE_DETECTOR_MIN_CONFIDENCE", 0.30)
    ocr_min_confidence = _float("OCR_MIN_CONFIDENCE", 0.80)
    ocr_gpu = os.getenv("OCR_GPU", "false").lower() in ("1", "true", "yes")
    anpr_enabled = os.getenv("ANPR_ENABLED", "true").lower() in ("1", "true", "yes")

    # FR13 / FR15 – challans and payments
    default_fines = _fines()
    challan_due_days = _int("CHALLAN_DUE_DAYS", 30)
    challan_auto_issue = os.getenv("CHALLAN_AUTO_ISSUE", "true").lower() in ("1", "true", "yes")
    # same vehicle + same violation type within this window -> one challan
    challan_duplicate_window_seconds = _int("CHALLAN_DUPLICATE_WINDOW_SECONDS", 120)
    overdue_check_minutes = _int("OVERDUE_CHECK_MINUTES", 15)


enforcement_settings = EnforcementSettings()
