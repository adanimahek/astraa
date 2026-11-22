"""MongoDB persistence for detected violations."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from .. import db
from .config import enforcement_settings as es
from .red_light import iou


class ViolationStatus:
    DETECTED = "detected"                 # FR10: event stored, no plate yet
    PENDING_REVIEW = "pending_review"     # FR11: plate uncertain -> manual verification
    VERIFIED = "verified"                 # plate confirmed (auto or manual)
    UNREGISTERED = "unregistered"         # FR12: plate not found in owner records
    CHALLAN_ISSUED = "challan_issued"     # FR13
    REJECTED = "rejected"                 # dismissed by an operator


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{now():%Y%m%d}-{secrets.token_hex(4).upper()}"


def ensure_indexes() -> None:
    v = db.violations
    v.create_index("violation_id", unique=True)
    v.create_index([("source.source_id", ASCENDING), ("event_key", ASCENDING)], unique=True)
    v.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    v.create_index("plate.number")


def _is_near_duplicate(source_id: str, ev: dict) -> bool:
    window = es.duplicate_window_seconds
    q = {"source.source_id": source_id, "lane": ev["lane"], "type": ev["violation_type"],
         "media_time": {"$gte": ev["timestamp"] - window, "$lte": ev["timestamp"] + window}}
    for other in db.violations.find(q, {"bbox": 1, "track_id": 1}):
        if other.get("track_id") == ev["track_id"]:
            return True
        if ev.get("bbox") and other.get("bbox") and iou(ev["bbox"], other["bbox"]) >= 0.3:
            return True
    return False


def save_events(events: List[dict], source: dict, user_email: str,
                base_time: Optional[datetime], time_basis: str) -> dict:
    """Insert violation events; returns ``{"inserted": [...docs], "duplicates": n}``."""
    inserted, duplicates = [], 0
    created = now()
    for ev in events:
        if _is_near_duplicate(source["source_id"], ev):
            duplicates += 1
            continue
        base = base_time or created
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        doc = {
            "violation_id": new_id("VIO"),
            "type": ev["violation_type"],
            "status": ViolationStatus.DETECTED,
            "source": source,
            "event_key": ev["event_key"],
            "track_id": ev["track_id"],
            "lane": ev["lane"],
            "approach": (ev.get("meta") or {}).get("approach") or ev["lane"],
            "media_time": ev["timestamp"],
            "occurred_at": base + timedelta(seconds=float(ev["timestamp"])),
            "occurred_at_basis": time_basis,
            "signal": {"state": ev["signal_state"], "red_started_at": ev["red_started_at"],
                       "time_into_red": ev["time_into_red"],
                       "previous_observation_at": ev["previous_timestamp"]},
            "vehicle_class": ev.get("vehicle_class"),
            "detection_confidence": ev.get("confidence"),
            "bbox": ev.get("bbox"),
            "meta": ev.get("meta") or {},
            "evidence": ev.get("evidence") or {},
            "plate": None,
            "created_by": user_email,
            "created_at": created,
            "updated_at": created,
            "history": [{"at": created, "by": user_email, "action": "detected"}],
        }
        try:
            db.violations.insert_one(doc)
        except DuplicateKeyError:
            duplicates += 1
            continue
        inserted.append(doc)
    return {"inserted": inserted, "duplicates": duplicates}


def add_history(violation_id: str, by: str, action: str, note: Optional[str] = None,
                **set_fields) -> None:
    entry = {"at": now(), "by": by, "action": action}
    if note:
        entry["note"] = note
    db.violations.update_one({"violation_id": violation_id},
                             {"$set": {**set_fields, "updated_at": entry["at"]},
                              "$push": {"history": entry}})


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def serialize(value):
    """JSON-friendly copy of a Mongo document (drops ``_id``, ISO datetimes)."""
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    return value
