"""Automatic number-plate recognition (ANPR).

Two pluggable stages, both pretrained and independent of the ASTRA vehicle
model (which is neither replaced nor retrained):

1. :class:`YoloPlateDetector` – a pretrained licence-plate YOLO model loaded
   from ``PLATE_DETECTOR_PATH`` (default ``models/anpr/license_plate_yolo11n.pt``,
   from ``morsetechlab/yolov11-license-plate-detection``).
2. :class:`EasyOcrEngine` – EasyOCR's pretrained English recogniser restricted
   to A-Z / 0-9.

Readings are normalised with :mod:`app.enforcement.plates`.  A reading is
only *auto-verified* when the plate format is valid and the combined
confidence clears ``OCR_MIN_CONFIDENCE``; everything else is routed to manual
verification with explicit reasons.
"""
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import plates
from .config import enforcement_settings as es

ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
Box = Tuple[float, float, float, float]


class AnprUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------- detectors
class YoloPlateDetector:
    def __init__(self, path: Optional[str] = None, min_conf: Optional[float] = None):
        self.path = path or es.plate_detector_path
        self.min_conf = es.plate_detector_min_confidence if min_conf is None else min_conf
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            import os
            if not os.path.isfile(self.path):
                raise AnprUnavailable(f"Plate detector weights not found: {self.path}")
            from ultralytics import YOLO
            self._model = YOLO(self.path)
        return self._model

    def detect(self, img: np.ndarray) -> List[Tuple[Box, float]]:
        with self._lock:
            res = self._load().predict(img, conf=self.min_conf, imgsz=640, verbose=False)[0]
        out = [(tuple(float(v) for v in b.xyxy[0]), float(b.conf)) for b in res.boxes]
        return sorted(out, key=lambda x: -x[1])


class EasyOcrEngine:
    def __init__(self, gpu: Optional[bool] = None):
        self.gpu = es.ocr_gpu if gpu is None else gpu
        self._reader = None
        self._lock = threading.Lock()

    def _load(self):
        if self._reader is None:
            try:
                import easyocr
            except ImportError as exc:
                raise AnprUnavailable("easyocr is not installed") from exc
            self._reader = easyocr.Reader(["en"], gpu=self.gpu, verbose=False)
        return self._reader

    def read(self, img: np.ndarray) -> List[Tuple[str, float, Box]]:
        with self._lock:
            rows = self._load().readtext(img, allowlist=ALNUM, detail=1, paragraph=False)
        out = []
        for poly, text, conf in rows:
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            out.append((text, float(conf), (min(xs), min(ys), max(xs), max(ys))))
        return out


# ------------------------------------------------------------------ helpers
def prepare_plate(img: np.ndarray, target_h: int = 96) -> np.ndarray:
    """Upscale + contrast-normalise a plate crop for OCR."""
    h, w = img.shape[:2]
    if h < target_h:
        s = target_h / max(1, h)
        img = cv2.resize(img, (int(w * s), target_h), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def join_lines(rows: Sequence[Tuple[str, float, Box]]) -> Tuple[str, float]:
    """Merge OCR fragments in reading order (handles two-row Indian plates)."""
    if not rows:
        return "", 0.0
    heights = [b[3] - b[1] for _, _, b in rows]
    line_tol = max(4.0, 0.5 * float(np.median(heights)))
    ordered = sorted(rows, key=lambda r: ((r[2][1] + r[2][3]) / 2, r[2][0]))
    lines, current, line_y = [], [], 0.0
    for r in ordered:
        y = (r[2][1] + r[2][3]) / 2
        if current and abs(y - line_y) > line_tol:
            lines.append(current)
            current = []
        if not current:
            line_y = y
        current.append(r)
    lines.append(current)
    text = "".join(t for line in lines for t, _, _ in sorted(line, key=lambda r: r[2][0]))
    chars = sum(len(plates.clean(t)) for t, _, _ in rows) or 1
    conf = sum(c * len(plates.clean(t)) for t, c, _ in rows) / chars  # char-weighted
    return text, conf


@dataclass
class PlateReading:
    number: Optional[str]
    formatted: Optional[str]
    raw_text: str
    ocr_confidence: float
    detector_confidence: Optional[float]
    confidence: float
    corrections: int
    plate_format: Optional[str]
    plate_box: Optional[Box]
    crop: Optional[np.ndarray] = field(default=None, repr=False)
    source_image: int = 0

    @property
    def valid(self) -> bool:
        return self.number is not None


@dataclass
class AnprResult:
    best: Optional[PlateReading]
    candidates: List[PlateReading]
    auto_verified: bool
    review_reasons: List[str]
    engine: str


class AnprService:
    CORRECTION_PENALTY = 0.93

    def __init__(self, detector=None, ocr=None, min_confidence: Optional[float] = None):
        self.detector = detector or YoloPlateDetector()
        self.ocr = ocr or EasyOcrEngine()
        self.min_confidence = es.ocr_min_confidence if min_confidence is None else min_confidence

    def _read_plate(self, crop: np.ndarray, det_conf: Optional[float], box, idx) -> PlateReading:
        raw, ocr_conf = join_lines(self.ocr.read(prepare_plate(crop)))
        parsed = plates.normalize(raw)
        conf = ocr_conf * (self.CORRECTION_PENALTY ** (parsed.corrections if parsed else 0))
        if det_conf is not None:
            conf *= min(1.0, 0.5 + det_conf)  # weak detections reduce trust
        return PlateReading(
            parsed.number if parsed else None, parsed.formatted if parsed else None,
            plates.clean(raw), round(ocr_conf, 4), None if det_conf is None else round(det_conf, 4),
            round(conf, 4), parsed.corrections if parsed else 0, parsed.kind if parsed else None,
            box, crop, idx)

    def recognize(self, images: Sequence[np.ndarray], max_plates: int = 2) -> AnprResult:
        candidates: List[PlateReading] = []
        plate_found = False
        for idx, img in enumerate(images):
            if img is None or img.size == 0:
                continue
            dets = self.detector.detect(img)[:max_plates]
            for box, det_conf in dets:
                x1, y1, x2, y2 = (int(round(v)) for v in box)
                crop = img[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                if crop.size == 0:
                    continue
                plate_found = True
                candidates.append(self._read_plate(crop, det_conf, box, idx))
        if not plate_found:  # fallback: OCR the lower half of the vehicle, never auto-verified
            for idx, img in enumerate(images):
                if img is not None and img.size:
                    h = img.shape[0]
                    candidates.append(self._read_plate(img[h // 2:], None, None, idx))
        candidates.sort(key=lambda c: (c.valid, c.confidence), reverse=True)
        best = candidates[0] if candidates else None

        reasons = []
        if not plate_found:
            reasons.append("plate_not_detected")
        if best is None or not best.raw_text:
            reasons.append("no_text_read")
        elif not best.valid:
            reasons.append("invalid_indian_format")
        elif best.confidence < self.min_confidence:
            reasons.append("low_confidence")
        valid_numbers = {c.number for c in candidates if c.valid and c.confidence >= self.min_confidence}
        if len(valid_numbers) > 1:
            reasons.append("conflicting_readings")
        return AnprResult(best, candidates, not reasons, reasons, "yolo-plate+easyocr")


_service: Optional[AnprService] = None


def service() -> AnprService:
    global _service
    if _service is None:
        _service = AnprService()
    return _service
