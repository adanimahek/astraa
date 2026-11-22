"""Red-light violation detection on uploaded traffic videos.

Uses the existing ASTRA YOLO11 weights (``settings.model_path``) with the
Ultralytics ByteTrack tracker to obtain persistent vehicle IDs.  A fresh model
instance is created per video so tracker state never leaks between jobs and
the shared detection model used by ``/api/detect`` is not affected.  The
weights file itself is only read.

Signal state is **operator supplied** per stop-line zone (see
:meth:`SignalTimeline.from_config`).  Time not covered by the config is
UNKNOWN and is never enforced.

Config JSON accepted by :func:`parse_video_config`::

    {
      "coordinates": "normalized",              # or "pixels"
      "zones": [{
        "name": "north",
        "stop_line": [[0.05, 0.62], [0.95, 0.62]],
        "before_point": [0.5, 0.95],            # any point on the approach side
        "margin": 0.01,                         # dead-band around the line
        "signal": {"mode": "timeline", "intervals": [...]}
      }],
      "recording_started_at": "2026-11-22T09:30:00+05:30"   # optional
    }
"""
import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .config import enforcement_settings as es
from .evidence import EvidenceStore, banner, crop
from .red_light import RedLightRule, Side, TrackObservation
from .signal import SignalState, SignalTimeline

Point = Tuple[float, float]
_LOCK = threading.Lock()  # one tracking job at a time keeps GPU/CPU usage bounded


@dataclass
class StopLineZone:
    name: str
    p1: Point
    p2: Point
    before_sign: float
    margin_px: float
    timeline: SignalTimeline

    def _signed(self, pt: Point) -> float:
        (x1, y1), (x2, y2) = self.p1, self.p2
        length = max(1e-6, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
        return ((x2 - x1) * (pt[1] - y1) - (y2 - y1) * (pt[0] - x1)) / length

    def _along(self, pt: Point) -> float:
        (x1, y1), (x2, y2) = self.p1, self.p2
        dx, dy = x2 - x1, y2 - y1
        return ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / max(1e-6, dx * dx + dy * dy)

    def side(self, pt: Point) -> Optional[Side]:
        """BEFORE/AFTER the line, or None inside the dead-band / outside the segment."""
        if not -0.05 <= self._along(pt) <= 1.05:
            return None
        d = self._signed(pt) * self.before_sign
        if abs(d) <= self.margin_px:
            return None
        return Side.BEFORE if d > 0 else Side.AFTER


@dataclass
class VideoConfig:
    zones: List[StopLineZone]
    recording_started_at: Optional[datetime]
    raw: dict


def _point(value, w: int, h: int, normalized: bool) -> Point:
    x, y = float(value[0]), float(value[1])
    return (x * w, y * h) if normalized else (x, y)


def parse_video_config(cfg: dict, width: int, height: int) -> VideoConfig:
    if not isinstance(cfg, dict) or not cfg.get("zones"):
        raise ValueError("Violation config must contain at least one stop-line zone")
    normalized = str(cfg.get("coordinates", "normalized")).lower() != "pixels"
    zones, names = [], set()
    for i, z in enumerate(cfg["zones"]):
        name = str(z.get("name") or f"zone{i + 1}")
        if name in names:
            raise ValueError(f"Duplicate zone name {name!r}")
        names.add(name)
        try:
            p1 = _point(z["stop_line"][0], width, height, normalized)
            p2 = _point(z["stop_line"][1], width, height, normalized)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError(f"Zone {name!r} needs stop_line [[x1, y1], [x2, y2]]")
        if p1 == p2:
            raise ValueError(f"Zone {name!r} stop line has zero length")
        before = _point(z.get("before_point") or ([0.5, 1.0] if normalized else [width / 2, height]),
                        width, height, normalized)
        margin = float(z.get("margin", 0.01))
        margin_px = margin * max(width, height) if normalized else margin
        zone = StopLineZone(name, p1, p2, 1.0, margin_px, SignalTimeline.from_config(z.get("signal")))
        sign = zone._signed(before)
        if abs(sign) < 1e-6:
            raise ValueError(f"Zone {name!r} before_point lies on the stop line")
        zone.before_sign = 1.0 if sign > 0 else -1.0
        zones.append(zone)
    started = cfg.get("recording_started_at")
    started_at = None
    if started:
        try:
            started_at = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("recording_started_at must be an ISO-8601 timestamp")
    return VideoConfig(zones, started_at, cfg)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_model_factory():
    from ultralytics import YOLO
    from ..config import settings
    return YOLO(settings.model_path)


def _draw_zone(img: np.ndarray, zone: StopLineZone, state: SignalState) -> None:
    colour = {SignalState.RED: (0, 0, 255), SignalState.YELLOW: (0, 200, 255),
              SignalState.GREEN: (0, 200, 0)}.get(state, (160, 160, 160))
    p1 = tuple(int(v) for v in zone.p1)
    p2 = tuple(int(v) for v in zone.p2)
    cv2.line(img, p1, p2, colour, 3)
    cv2.putText(img, f"{zone.name}: {state.value.upper()}", (p1[0], max(15, p1[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2, cv2.LINE_AA)


def _annotate(frame, zones, t, box, label, title) -> np.ndarray:
    img = frame.copy()
    for z in zones:
        _draw_zone(img, z, z.timeline.state_at(t))
    if box is not None:
        x1, y1, x2, y2 = (int(v) for v in box)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 3)
        cv2.putText(img, label, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 0, 255), 2, cv2.LINE_AA)
    return banner(img, title)


def detect_red_light_video(
    path: str,
    config: dict,
    conf: float = 0.4,
    analyse_fps: Optional[int] = None,
    max_frames: Optional[int] = None,
    model_factory: Optional[Callable] = None,
    evidence: Optional[EvidenceStore] = None,
    source_id: Optional[str] = None,
) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("Could not open the video")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    try:
        vcfg = parse_video_config(config, width, height)
    except ValueError:
        cap.release()
        raise
    analyse_fps = analyse_fps or es.video_analyse_fps
    max_frames = max_frames or es.video_max_frames
    step = max(1, round(fps / analyse_fps))
    source_id = source_id or file_sha256(path)
    evidence = evidence or EvidenceStore(es.evidence_dir)
    rule = RedLightRule(es.red_light_grace_seconds, es.exempt_vehicle_classes,
                        es.duplicate_window_seconds)

    events: List[dict] = []
    best_crop: Dict[str, Tuple[float, np.ndarray, float]] = {}
    last_seen: Dict[str, Tuple[float, list]] = {}
    prev_frame, prev_t = None, None
    unknown_signal_frames = analysed = idx = 0

    with _LOCK:
        tracker_model = (model_factory or _default_model_factory)()
        try:
            while analysed < max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % step:
                    idx += 1
                    continue
                t = idx / fps
                idx += 1
                analysed += 1
                states = {z.name: z.timeline.state_at(t) for z in vcfg.zones}
                for z in vcfg.zones:
                    rule.update_signal(z.name, t, states[z.name])
                if all(s is SignalState.UNKNOWN for s in states.values()):
                    unknown_signal_frames += 1

                res = tracker_model.track(frame, persist=True, conf=conf, imgsz=640,
                                          tracker=es.tracker, verbose=False)[0]
                boxes = res.boxes
                if boxes is not None and boxes.id is not None:
                    for b_id, b_xyxy, b_cls, b_conf in zip(boxes.id.tolist(), boxes.xyxy.tolist(),
                                                           boxes.cls.tolist(), boxes.conf.tolist()):
                        tid = str(int(b_id))
                        box = [round(float(v), 1) for v in b_xyxy]
                        cls_name = res.names[int(b_cls)]
                        ref = ((box[0] + box[2]) / 2, box[3])  # bottom-centre ≈ wheel contact
                        area = (box[2] - box[0]) * (box[3] - box[1])
                        if tid not in best_crop or area > best_crop[tid][0]:
                            c = crop(frame, box)
                            if c is not None:
                                best_crop[tid] = (area, c, t)
                        prev_box = last_seen.get(tid, (None, None))[1]
                        last_seen[tid] = (t, box)
                        for z in vcfg.zones:
                            side = z.side(ref)
                            if side is None:
                                continue
                            ev = rule.observe(TrackObservation(
                                track_id=tid, timestamp=t, side=side, signal_state=states[z.name],
                                lane=z.name, vehicle_class=cls_name, confidence=round(float(b_conf), 3),
                                bbox=tuple(box), position=ref,
                                meta={"frame_index": idx - 1, "previous_bbox": prev_box}))
                            if ev is not None:
                                events.append(_save_event(ev, evidence, source_id, frame, prev_frame,
                                                          prev_t, vcfg.zones, best_crop.get(tid)))
                prev_frame, prev_t = frame, t
                # bounded memory: forget tracks not seen for 30 s
                stale = [k for k, (seen, _) in last_seen.items() if t - seen > 30]
                for k in stale:
                    last_seen.pop(k, None)
                    best_crop.pop(k, None)
                rule.forget_stale(t)
        finally:
            cap.release()

    if analysed == 0:
        raise ValueError("No frames could be analysed")
    return {
        "source_id": source_id,
        "video": {"fps": round(fps, 2), "width": width, "height": height,
                  "frames_analysed": analysed, "analysis_step": step},
        "recording_started_at": vcfg.recording_started_at,
        "unknown_signal_frames": unknown_signal_frames,
        "signal_config": vcfg.raw,
        "rule_stats": rule.stats,
        "events": events,
    }


def _save_event(ev, evidence: EvidenceStore, source_id: str, frame, prev_frame, prev_t,
                zones, best) -> dict:
    folder = evidence.folder("video", source_id[:16], f"{ev.lane}_{ev.track_id}")
    label = f"#{ev.track_id} {ev.vehicle_class or ''}".strip()
    title = [f"RED-LIGHT VIOLATION  zone={ev.lane}  track={ev.track_id}",
             f"t={ev.timestamp:.2f}s  red for {ev.time_into_red:.2f}s  class={ev.vehicle_class}"]
    files = {"scene": evidence.save_image(folder, "scene.jpg",
                                          _annotate(frame, zones, ev.timestamp, ev.bbox, label, title))}
    if prev_frame is not None and prev_t is not None:
        pre_title = [f"BEFORE STOP LINE ON RED  zone={ev.lane}  track={ev.track_id}",
                     f"t={prev_t:.2f}s"]
        files["pre_crossing"] = evidence.save_image(
            folder, "pre_crossing.jpg",
            _annotate(prev_frame, zones, prev_t, ev.meta.get("previous_bbox"), label, pre_title))
    vehicle = crop(frame, ev.bbox) if ev.bbox else None
    crops = []
    if vehicle is not None:
        crops.append(evidence.save_image(folder, "vehicle.jpg", vehicle, 95))
    if best is not None:
        crops.append(evidence.save_image(folder, "vehicle_best.jpg", best[1], 95))
    files["vehicle_crops"] = crops
    out = ev.to_dict()
    out["meta"].pop("previous_bbox", None)
    out["evidence"] = files
    return out
