import time, uuid
from typing import Optional
import cv2
import numpy as np
from ultralytics import YOLO
from .config import settings

EMERGENCY = {"Ambulance", "Fire Truck"}
APPROACHES = ("north", "south", "east", "west")
_model = None

def model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(settings.model_path)  # loaded once, reused for every request
    return _model

def _read(res):
    counts, dets = {}, []
    for b in res.boxes:
        name, conf = res.names[int(b.cls)], float(b.conf)
        x1, y1, x2, y2 = (round(float(v), 1) for v in b.xyxy[0])
        counts[name] = counts.get(name, 0) + 1
        dets.append({"class": name, "confidence": round(conf, 3), "box": [x1, y1, x2, y2]})
    return counts, dets

def _volume_level(vehicles: int) -> str:
    if vehicles < 8:
        return "Low"
    if vehicles < 20:
        return "Medium"
    return "High"

def _approach_counts(dets: list, width: int, height: int) -> dict:
    counts = {approach: 0 for approach in APPROACHES}
    counts["intersection"] = 0
    for detection in dets:
        x1, y1, x2, y2 = detection["box"]
        x, y = (x1 + x2) / 2, (y1 + y2) / 2
        dx = (x - width / 2) / width
        dy = (y - height / 2) / height
        if abs(dx) <= 0.06 and abs(dy) <= 0.06:
            approach = "intersection"
        elif abs(dx) >= abs(dy):
            approach = "east" if dx > 0 else "west"
        else:
            approach = "south" if dy > 0 else "north"
        counts[approach] += 1
    return counts

def _traffic_analysis(vehicles: int, approach_counts: Optional[dict], basis: str) -> dict:
    return {
        "traffic_volume": {
            "level": _volume_level(vehicles),
            "vehicles": vehicles,
            "basis": basis,
        },
        "approach_counts": approach_counts,
        "approach_method": (
            "Approximate image-relative zones; assumes a centered, north-up intersection view."
            if approach_counts is not None
            else None
        ),
    }

def _save(img) -> str:
    name = f"{uuid.uuid4().hex}.jpg"
    cv2.imwrite(f"{settings.results_dir}/{name}", img)
    return f"/results/{name}"

def detect_image(data: bytes, conf: float, intersection_view: bool = False) -> dict:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read the image")
    t = time.time()
    res = model().predict(img, conf=conf, imgsz=640, verbose=False)[0]
    counts, dets = _read(res)
    total = len(dets)
    avg = sum(d["confidence"] for d in dets) / len(dets) if dets else 0.0
    approach_counts = _approach_counts(dets, img.shape[1], img.shape[0]) if intersection_view else None
    return {"type": "image", "total_vehicles": total, "counts": counts, "detections": dets,
            "avg_confidence": round(avg, 3), "emergency_detected": bool(EMERGENCY & counts.keys()),
            "processing_seconds": round(time.time() - t, 2), "annotated_url": _save(res.plot()),
            "width": img.shape[1], "height": img.shape[0],
            "traffic_analysis": _traffic_analysis(total, approach_counts, "vehicles detected in the image")}

def detect_live_frame(frame, conf: float = 0.5) -> dict:
    height, width = frame.shape[:2]
    scale = min(1.0, 640 / max(width, height))
    if scale < 1:
        frame = cv2.resize(
            frame,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    result = model().predict(frame, conf=conf, imgsz=640, verbose=False)[0]
    counts, detections = _read(result)
    encoded, buffer = cv2.imencode(
        ".jpg", result.plot(), [cv2.IMWRITE_JPEG_QUALITY, 70]
    )
    if not encoded:
        raise RuntimeError("Could not encode the annotated live camera frame")
    return {
        "counts": counts,
        "detections": detections,
        "emergency_detected": bool(EMERGENCY & counts.keys()),
        "annotated_frame": buffer.tobytes(),
        "width": frame.shape[1],
        "height": frame.shape[0],
    }

def detect_video(path: str, conf: float, analyse_fps: int = 5, max_frames: int = 600,
                 intersection_view: bool = False) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("Could not open the video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, round(fps / analyse_fps))
    t = time.time()
    peak_counts, peak_approaches, peak_total, peak_img = {}, None, -1, None
    vehicle_sum = 0
    confs, em_frames, done, idx = [], 0, 0, 0
    while done < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            res = model().predict(frame, conf=conf, imgsz=640, verbose=False)[0]
            counts, dets = _read(res)
            total = len(dets)
            confs += [d["confidence"] for d in dets]
            em_frames += bool(EMERGENCY & counts.keys())
            vehicle_sum += total
            if total > peak_total:
                peak_total, peak_counts, peak_img = total, counts, res.plot()
                peak_approaches = (
                    _approach_counts(dets, frame.shape[1], frame.shape[0])
                    if intersection_view else None
                )
            done += 1
        idx += 1
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if peak_img is None:
        raise ValueError("No frames could be analysed")
    el = time.time() - t
    return {"type": "video", "frames_analysed": done, "video_fps": round(fps, 1), "total_frames": total_frames,
            "peak_vehicles": peak_total, "counts": peak_counts,  # highest simultaneous counts seen in one frame
            "average_vehicles_per_frame": round(vehicle_sum / done, 2),
            "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0.0,
            "emergency_detected": em_frames > 0, "emergency_frames": em_frames,
            "processing_seconds": round(el, 2), "analysis_fps": round(done / el, 1) if el else 0,
            "annotated_url": _save(peak_img),
            "traffic_analysis": _traffic_analysis(
                peak_total,
                peak_approaches,
                "peak simultaneous vehicles in one analysed frame",
            )}
