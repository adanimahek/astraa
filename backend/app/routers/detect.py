import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from ..auth import current_user
from ..db import detections
from .. import yolo_service as yolo

router = APIRouter(prefix="/api/detect", tags=["detection"])
IMG_MAX, VID_MAX = 10 * 1024 * 1024, 200 * 1024 * 1024
SUMO_EMERGENCY_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "sumo"
    / "scripts"
    / "simulate_emergency.py"
)

def _store(user: dict, filename: str, result: dict) -> dict:
    doc = {**result, "filename": filename, "user": user["email"], "created_at": datetime.now(timezone.utc)}
    result["id"] = str(detections.insert_one(doc).inserted_id)
    return result

@router.post("/image")
def detect_image(file: UploadFile = File(...), conf: float = Form(0.5, ge=0.1, le=0.9),
                 intersection_view: bool = Form(False), user: dict = Depends(current_user)):
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Only JPG or PNG images are supported")
    data = file.file.read(IMG_MAX + 1)
    if len(data) > IMG_MAX:
        raise HTTPException(413, "Image is larger than 10 MB")
    try:
        return _store(user, file.filename, yolo.detect_image(data, conf, intersection_view))
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/video")
def detect_video(file: UploadFile = File(...), conf: float = Form(0.5, ge=0.1, le=0.9),
                 intersection_view: bool = Form(False), user: dict = Depends(current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".mp4", ".avi", ".mov"):
        raise HTTPException(400, "Only MP4, AVI or MOV videos are supported")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            size = 0
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > VID_MAX:
                    raise HTTPException(413, "Video is larger than 200 MB")
                tmp.write(chunk)
        return _store(user, file.filename, yolo.detect_video(tmp_path, conf, intersection_view=intersection_view))
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.post("/simulate/emergency")
def simulate_emergency(
    detection_id: str = Form(...),
    approach: Literal["north", "south", "east", "west"] = Form(...),
    user: dict = Depends(current_user),
):
    if not ObjectId.is_valid(detection_id):
        raise HTTPException(400, "Invalid detection ID")
    detection = detections.find_one({"_id": ObjectId(detection_id)})
    if not detection:
        raise HTTPException(404, "Detection not found")
    if user["role"] != "Administrator" and detection.get("user") != user["email"]:
        raise HTTPException(403, "You cannot simulate another user's detection")
    if not detection.get("emergency_detected"):
        raise HTTPException(409, "This detection contains no emergency vehicle")
    if not SUMO_EMERGENCY_SCRIPT.is_file():
        raise HTTPException(503, f"SUMO emergency script not found: {SUMO_EMERGENCY_SCRIPT}")

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SUMO_EMERGENCY_SCRIPT),
                "--approach",
                approach,
            ],
            cwd=SUMO_EMERGENCY_SCRIPT.parents[2],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "SUMO emergency simulation exceeded 120 seconds") from exc
    except OSError as exc:
        raise HTTPException(503, f"Could not start SUMO emergency simulation: {exc}") from exc

    if completed.returncode != 0:
        details = completed.stderr.strip()[-2000:] or "SUMO exited without an error message"
        raise HTTPException(500, f"SUMO emergency simulation failed: {details}")

    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "SUMO returned an invalid emergency simulation result") from exc
    detections.update_one(
        {"_id": ObjectId(detection_id)},
        {"$set": {"emergency_simulation": result}},
    )
    return result

@router.get("/history")
def history(limit: int = 20, user: dict = Depends(current_user)):
    q = {} if user["role"] == "Administrator" else {"user": user["email"]}
    out = []
    for d in detections.find(q).sort("created_at", -1).limit(limit):
        d["id"] = str(d.pop("_id")); d.pop("detections", None); out.append(d)
    return out
