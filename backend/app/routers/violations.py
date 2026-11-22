"""Violation detection & review endpoints (staff: Administrator / Traffic Operator)."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db
from ..auth import current_user
from ..enforcement import pipeline, store
from ..enforcement.config import enforcement_settings as es
from ..enforcement.evidence import EvidenceStore

router = APIRouter(prefix="/api/violations", tags=["violations"])
VID_MAX = 200 * 1024 * 1024
SUMO_VIOLATION_SCRIPT = (Path(__file__).resolve().parents[3] / "sumo" / "scripts"
                         / "detect_red_light_violations.py")

EXAMPLE_VIDEO_CONFIG = {
    "coordinates": "normalized",
    "recording_started_at": None,
    "zones": [{
        "name": "north",
        "stop_line": [[0.05, 0.62], [0.95, 0.62]],
        "before_point": [0.5, 0.95],
        "margin": 0.01,
        "signal": {"mode": "timeline", "intervals": [
            {"start": 0, "end": 20, "state": "green"},
            {"start": 20, "end": 23, "state": "yellow"},
            {"start": 23, "end": 60, "state": "red"},
        ]},
    }],
}


def evidence_store() -> EvidenceStore:
    return EvidenceStore(es.evidence_dir)


def _post_process(docs: list, user: dict) -> list:
    """Downstream pipeline: ANPR / simulated plate → owner lookup → challan."""
    return pipeline.process_new(docs, user["email"])


def _summary(result: dict, saved: dict, user: dict) -> dict:
    docs = _post_process(saved["inserted"], user)
    return {
        "source_id": result["source_id"],
        "violations_detected": len(result["events"]),
        "violations_stored": len(saved["inserted"]),
        "duplicates_skipped": saved["duplicates"],
        "rule_stats": result.get("rule_stats"),
        "violations": [store.serialize(d) for d in docs],
        **{k: result[k] for k in ("video", "unknown_signal_frames", "simulated_seconds",
                                  "red_light_ignoring_vehicles") if k in result},
    }


@router.get("/config/example")
def example_config(_: dict = Depends(current_user)):
    return EXAMPLE_VIDEO_CONFIG


@router.post("/detect/video")
def detect_video(file: UploadFile = File(...), config: str = Form(...),
                 conf: float = Form(0.4, ge=0.1, le=0.9), user: dict = Depends(current_user)):
    from ..enforcement.video import detect_red_light_video

    try:
        cfg = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(400, "config must be valid JSON")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".mp4", ".avi", ".mov"):
        raise HTTPException(400, "Only MP4, AVI or MOV videos are supported")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            size = 0
            chunk = file.file.read(1024 * 1024)
            while chunk:
                size += len(chunk)
                if size > VID_MAX:
                    raise HTTPException(413, "Video is larger than 200 MB")
                tmp.write(chunk)
                chunk = file.file.read(1024 * 1024)
        try:
            result = detect_red_light_video(tmp_path, cfg, conf=conf, evidence=evidence_store())
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
    started = result.get("recording_started_at")
    source = {"kind": "video", "source_id": result["source_id"], "filename": file.filename,
              "signal_config": result["signal_config"]}
    saved = store.save_events(result["events"], source, user["email"], started,
                              "recording_start" if started else "upload_time")
    return _summary(result, saved, user)


class SumoRun(BaseModel):
    seed: int = 101
    duration_seconds: float = Field(600, ge=60, le=2400)
    violation_probability: float = Field(0.05, ge=0, le=1)
    gui: bool = False


@router.post("/detect/sumo")
def detect_sumo(body: SumoRun, user: dict = Depends(current_user)):
    if not SUMO_VIOLATION_SCRIPT.is_file():
        raise HTTPException(503, f"SUMO violation script not found: {SUMO_VIOLATION_SCRIPT}")
    cmd = [sys.executable, "-B", str(SUMO_VIOLATION_SCRIPT), "--seed", str(body.seed),
           "--duration", str(body.duration_seconds),
           "--violation-probability", str(body.violation_probability),
           "--grace", str(es.sumo_red_light_grace_seconds),
           "--evidence-dir", es.evidence_dir]
    if body.gui:
        cmd.append("--gui")
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(cmd, cwd=SUMO_VIOLATION_SCRIPT.parents[2], capture_output=True,
                                   text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "SUMO violation run exceeded 300 seconds") from exc
    except OSError as exc:
        raise HTTPException(503, f"Could not start SUMO: {exc}") from exc
    if completed.returncode != 0:
        details = completed.stderr.strip()[-2000:] or "SUMO exited without an error message"
        raise HTTPException(500, f"SUMO violation run failed: {details}")
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "SUMO returned an invalid violation result") from exc
    source = {"kind": "sumo", "source_id": result["source_id"], "seed": result["seed"],
              "violation_probability": result["violation_probability"]}
    saved = store.save_events(result["events"], source, user["email"], started, "simulation")
    return _summary(result, saved, user)


@router.get("")
def list_violations(status: Optional[str] = None, type: Optional[str] = None,
                    limit: int = Query(50, ge=1, le=500), skip: int = Query(0, ge=0),
                    _: dict = Depends(current_user)):
    q = {}
    if status:
        q["status"] = status
    if type:
        q["type"] = type
    cursor = db.violations.find(q, {"history": 0}).sort("created_at", -1).skip(skip).limit(limit)
    return {"total": db.violations.count_documents(q),
            "items": [store.serialize(d) for d in cursor]}


def get_violation_or_404(violation_id: str) -> dict:
    doc = db.violations.find_one({"violation_id": violation_id})
    if not doc:
        raise HTTPException(404, "Violation not found")
    return doc


@router.get("/review/queue")
def review_queue(limit: int = Query(50, ge=1, le=500), _: dict = Depends(current_user)):
    q = {"status": store.ViolationStatus.PENDING_REVIEW}
    cursor = db.violations.find(q, {"history": 0}).sort("created_at", 1).limit(limit)
    return {"total": db.violations.count_documents(q),
            "items": [store.serialize(d) for d in cursor]}


class PlateVerification(BaseModel):
    plate_number: str = Field(..., min_length=6, max_length=16)
    note: Optional[str] = Field(None, max_length=500)


class Rejection(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


def _review_call(fn, *args):
    try:
        return store.serialize(fn(*args))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except pipeline.ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except pipeline.ReviewError as exc:
        raise HTTPException(422, str(exc))


@router.post("/{violation_id}/verify-plate")
def verify_plate(violation_id: str, body: PlateVerification, user: dict = Depends(current_user)):
    return _review_call(pipeline.verify_plate, violation_id, body.plate_number, user["email"],
                        body.note)


@router.post("/{violation_id}/reject")
def reject_violation(violation_id: str, body: Rejection, user: dict = Depends(current_user)):
    return _review_call(pipeline.reject, violation_id, user["email"], body.reason)


@router.post("/{violation_id}/resolve-owner")
def resolve_owner(violation_id: str, user: dict = Depends(current_user)):
    """Re-run owner lookup, e.g. after an unknown registration was added to the registry."""
    doc = get_violation_or_404(violation_id)
    if doc["status"] not in (store.ViolationStatus.VERIFIED, store.ViolationStatus.UNREGISTERED):
        raise HTTPException(409, f"Owner lookup needs a verified plate (status {doc['status']!r})")
    return store.serialize(pipeline.process_verified(doc, user["email"]))


@router.post("/{violation_id}/rerun-anpr")
def rerun_anpr(violation_id: str, user: dict = Depends(current_user)):
    doc = get_violation_or_404(violation_id)
    if doc["status"] not in (store.ViolationStatus.DETECTED, store.ViolationStatus.PENDING_REVIEW):
        raise HTTPException(409, f"Cannot re-run ANPR for status {doc['status']!r}")
    if doc["source"]["kind"] == "sumo":
        raise HTTPException(409, "SUMO violations use simulated plates")
    return store.serialize(pipeline.process_new([doc], user["email"])[0])


@router.get("/{violation_id}")
def get_violation(violation_id: str, _: dict = Depends(current_user)):
    return store.serialize(get_violation_or_404(violation_id))


def evidence_file(doc: dict, kind: str, index: int = 0) -> FileResponse:
    ev = doc.get("evidence") or {}
    if kind in ("vehicle_crops", "plate_crops"):
        items = ev.get(kind) or []
        rel = items[index] if 0 <= index < len(items) else None
    else:
        rel = ev.get(kind)
    path = evidence_store().resolve(rel) if isinstance(rel, str) else None
    if not path:
        raise HTTPException(404, "Evidence not found")
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/{violation_id}/evidence/{kind}")
def get_evidence(violation_id: str, kind: str, index: int = 0, _: dict = Depends(current_user)):
    return evidence_file(get_violation_or_404(violation_id), kind, index)
