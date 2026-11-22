"""Automatic e-challan generation.

Duplicate protection (three layers):

1. one challan per violation – unique index on ``challans.violation_id``;
2. one challan per vehicle per offence window – same registration + type
   within ``CHALLAN_DUPLICATE_WINDOW_SECONDS`` is linked to the existing
   challan instead of creating a new one;
3. challan numbers come from an atomic counter and are uniquely indexed.
"""
from datetime import timedelta
from typing import Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .. import db
from . import fines, notifications
from .config import enforcement_settings as es
from .store import ViolationStatus as S, add_history, as_utc, now


class ChallanStatus:
    UNPAID = "unpaid"
    PAID = "paid"
    CANCELLED = "cancelled"


class ChallanError(ValueError):
    pass


def ensure_indexes() -> None:
    c = db.challans
    c.create_index("challan_number", unique=True)
    c.create_index("violation_id", unique=True)
    c.create_index([("owner_id", ASCENDING), ("issued_at", DESCENDING)])
    c.create_index([("registration_number", ASCENDING), ("violation_type", ASCENDING),
                    ("occurred_at", ASCENDING)])
    c.create_index([("status", ASCENDING), ("due_date", ASCENDING)])
    fines.ensure_rules()
    notifications.ensure_indexes()
    from . import payments
    payments.ensure_indexes()


def next_challan_number(at=None) -> str:
    year = (at or now()).year
    counter = db.counters.find_one_and_update(
        {"_id": f"challan-{year}"}, {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER)
    return f"ECH-{year}-{counter['seq']:07d}"


def _duplicate_of(violation: dict) -> Optional[dict]:
    window = timedelta(seconds=es.challan_duplicate_window_seconds)
    at = as_utc(violation["occurred_at"])
    return db.challans.find_one({
        "registration_number": violation["plate"]["number"],
        "violation_type": violation["type"],
        "status": {"$ne": ChallanStatus.CANCELLED},
        "occurred_at": {"$gte": at - window, "$lte": at + window},
    })


def issue(violation: dict, issued_by: str) -> dict:
    """Create the challan for a verified, owner-matched violation.

    Returns the challan document (an existing one if this is a duplicate).
    """
    vid = violation["violation_id"]
    existing = db.challans.find_one({"violation_id": vid})
    if existing:
        return existing
    if violation.get("status") != S.VERIFIED:
        raise ChallanError(f"Violation must be verified (status {violation.get('status')!r})")
    plate = violation.get("plate") or {}
    if not plate.get("verified") or not plate.get("number"):
        raise ChallanError("Registration number has not been verified")
    if not violation.get("owner"):
        raise ChallanError("No registered owner for this vehicle")
    rule = fines.get_rule(violation["type"])
    if not rule or not rule.get("active", True):
        raise ChallanError(f"No active fine rule for {violation['type']!r}")

    dup = _duplicate_of(violation)
    if dup:
        add_history(vid, issued_by, "duplicate_of_challan", dup["challan_number"],
                    status=S.CHALLAN_ISSUED, challan_number=dup["challan_number"],
                    duplicate_of=dup["challan_number"])
        return dup

    reg = plate["number"]
    previous = db.challans.count_documents({"registration_number": reg,
                                            "violation_type": violation["type"],
                                            "status": {"$ne": ChallanStatus.CANCELLED}})
    repeat = previous > 0 and rule.get("repeat_amount")
    amount = int(rule["repeat_amount"] if repeat else rule["amount"])
    issued_at = now()
    doc = {
        "violation_id": vid,
        "violation_type": violation["type"],
        "violation_label": rule["label"],
        "legal_section": rule["legal_section"],
        "occurred_at": as_utc(violation["occurred_at"]),
        "location": {"source": violation["source"].get("kind"), "approach": violation.get("approach"),
                     "lane": violation.get("lane")},
        "registration_number": reg,
        "vehicle": violation.get("vehicle"),
        "owner_id": violation["owner"]["owner_id"],
        "owner": violation["owner"],
        "evidence": violation.get("evidence") or {},
        "signal": violation.get("signal"),
        "fine": {"amount": amount, "currency": rule.get("currency", "INR"),
                 "repeat_offence": bool(repeat), "previous_offences": previous,
                 "rule_version": rule.get("version", 1)},
        "issued_at": issued_at,
        "due_date": issued_at + timedelta(days=int(rule.get("due_days", es.challan_due_days))),
        "status": ChallanStatus.UNPAID,
        "payment": None,
        "issued_by": issued_by,
        "history": [{"at": issued_at, "by": issued_by, "action": "issued"}],
    }
    for _ in range(5):  # retry only on a (theoretical) number collision
        doc["challan_number"] = next_challan_number(issued_at)
        try:
            db.challans.insert_one(doc)
            break
        except DuplicateKeyError as exc:
            if "violation_id" in str(exc):  # concurrent issue for same violation
                return db.challans.find_one({"violation_id": vid})
            doc.pop("_id", None)
    else:
        raise ChallanError("Could not allocate a unique challan number")
    add_history(vid, issued_by, "challan_issued", doc["challan_number"],
                status=S.CHALLAN_ISSUED, challan_number=doc["challan_number"])
    notifications.challan_issued(doc)
    return doc


def cancel(challan_number: str, by: str, reason: str) -> dict:
    ch = db.challans.find_one_and_update(
        {"challan_number": challan_number, "status": ChallanStatus.UNPAID},
        {"$set": {"status": ChallanStatus.CANCELLED, "cancelled_at": now(),
                  "cancellation_reason": reason},
         "$push": {"history": {"at": now(), "by": by, "action": "cancelled", "note": reason}}},
        return_document=ReturnDocument.AFTER)
    if ch is None:
        if not db.challans.find_one({"challan_number": challan_number}):
            raise LookupError("Challan not found")
        raise ChallanError("Only unpaid challans can be cancelled")
    add_history(ch["violation_id"], by, "challan_cancelled", reason)
    notifications.challan_cancelled(ch)
    return ch
