"""Owner notifications.

Every notification is stored as an in-app message (``notifications``).  For
owners with an e-mail / phone, a *simulated* e-mail/SMS record is written to
``notification_outbox`` with ``status: "simulated"`` – nothing is sent to a
real gateway.  A real provider can later be plugged in by consuming the
outbox.
"""
from typing import Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from .. import db
from .store import new_id, now

KINDS = ("challan_issued", "challan_cancelled", "payment_received", "challan_overdue")


def ensure_indexes() -> None:
    db.notifications.create_index("notification_id", unique=True)
    db.notifications.create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
    # one notification of a kind per challan (idempotent re-runs, e.g. overdue job)
    db.notifications.create_index([("owner_id", ASCENDING), ("kind", ASCENDING),
                                   ("challan_number", ASCENDING), ("dedupe_key", ASCENDING)],
                                  unique=True)


def notify(owner: dict, kind: str, title: str, message: str,
           challan_number: Optional[str] = None, dedupe_key: str = "") -> Optional[dict]:
    if kind not in KINDS:
        raise ValueError(f"Unknown notification kind {kind!r}")
    owner_id = owner["owner_id"]
    if db.notifications.find_one({"owner_id": owner_id, "kind": kind,
                                  "challan_number": challan_number, "dedupe_key": dedupe_key}):
        return None
    ts = now()
    doc = {"notification_id": new_id("NTF"), "owner_id": owner_id, "kind": kind, "title": title,
           "message": message, "challan_number": challan_number, "dedupe_key": dedupe_key,
           "read": False, "created_at": ts}
    try:
        db.notifications.insert_one(doc)
    except DuplicateKeyError:  # concurrent duplicate
        return None
    for channel, address in (("email", owner.get("email")), ("sms", owner.get("phone"))):
        if address:
            db.notification_outbox.insert_one({
                "notification_id": doc["notification_id"], "channel": channel, "to": address,
                "subject": title, "body": message, "status": "simulated", "created_at": ts})
    return doc


def challan_issued(ch: dict) -> None:
    notify(ch["owner"], "challan_issued", f"New e-challan {ch['challan_number']}",
           f"A {ch['violation_label'].lower()} was recorded for vehicle "
           f"{ch['registration_number']}. Fine ₹{ch['fine']['amount']} is due by "
           f"{ch['due_date']:%d %b %Y}.", ch["challan_number"])


def challan_cancelled(ch: dict) -> None:
    notify(ch["owner"], "challan_cancelled", f"E-challan {ch['challan_number']} cancelled",
           f"Challan {ch['challan_number']} for {ch['registration_number']} was cancelled: "
           f"{ch.get('cancellation_reason', '')}", ch["challan_number"])
