"""Vehicle-owner portal.

Every query is scoped by the ``owner_id`` stored on the authenticated user –
never by a request parameter – so owners can only see their own records.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db
from ..auth import owner_only
from ..enforcement.store import serialize
from .violations import evidence_store

router = APIRouter(prefix="/api/owner", tags=["vehicle owner"])

# Fields an owner may see on a challan (internal review data is excluded).
CHALLAN_FIELDS = {"_id": 0, "history": 0, "issued_by": 0}


def present(ch: dict) -> dict:
    """Owner-facing challan with display status (FR15 adds overdue)."""
    from ..enforcement import payments  # FR15

    out = serialize(ch)
    out["display_status"] = payments.display_status(ch)
    out["is_overdue"] = out["display_status"] == "overdue"
    return out


def _own_challan(user: dict, challan_number: str) -> dict:
    ch = db.challans.find_one({"challan_number": challan_number, "owner_id": user["owner_id"]},
                              CHALLAN_FIELDS)
    if not ch:  # 404 (not 403) so other owners' challan numbers are not disclosed
        raise HTTPException(404, "Challan not found")
    return ch


@router.get("/dashboard")
def dashboard(user: dict = Depends(owner_only)):
    from ..enforcement import payments

    oid = user["owner_id"]
    owner = db.owners.find_one({"owner_id": oid}, {"_id": 0})
    vehicles = list(db.vehicles.find({"owner_id": oid}, {"_id": 0}).sort("registration_number", 1))
    all_challans = list(db.challans.find({"owner_id": oid}, CHALLAN_FIELDS).sort("issued_at", -1))
    summary = payments.summarize(all_challans)
    per_vehicle = {}
    for ch in all_challans:
        reg = ch["registration_number"]
        row = per_vehicle.setdefault(reg, {"challans": 0, "outstanding": 0})
        row["challans"] += 1
        if ch["status"] == "unpaid":
            row["outstanding"] += ch["fine"]["amount"]
    for v in vehicles:
        v.update(per_vehicle.get(v["registration_number"], {"challans": 0, "outstanding": 0}))
    return {
        "owner": serialize(owner),
        "vehicles": serialize(vehicles),
        "summary": summary,
        "recent_challans": [present(c) for c in all_challans[:5]],
        "unread_notifications": db.notifications.count_documents({"owner_id": oid, "read": False}),
    }


@router.get("/vehicles")
def my_vehicles(user: dict = Depends(owner_only)):
    return serialize(list(db.vehicles.find({"owner_id": user["owner_id"]}, {"_id": 0})))


@router.get("/challans")
def my_challans(status: Optional[str] = None, user: dict = Depends(owner_only)):
    from ..enforcement import payments

    q = {"owner_id": user["owner_id"]}
    q.update(payments.status_filter(status))
    return [present(c) for c in db.challans.find(q, CHALLAN_FIELDS).sort("issued_at", -1)]


@router.get("/challans/{challan_number}")
def my_challan(challan_number: str, user: dict = Depends(owner_only)):
    return present(_own_challan(user, challan_number))


@router.get("/challans/{challan_number}/evidence/{kind}")
def my_evidence(challan_number: str, kind: str, index: int = 0, user: dict = Depends(owner_only)):
    ch = _own_challan(user, challan_number)
    if kind not in ("scene", "scene_zoom", "pre_crossing", "vehicle_crops", "plate_crops"):
        raise HTTPException(404, "Evidence not found")
    ev = ch.get("evidence") or {}
    rel = ev.get(kind)
    if isinstance(rel, list):
        rel = rel[index] if 0 <= index < len(rel) else None
    path = evidence_store().resolve(rel) if isinstance(rel, str) else None
    if not path:
        raise HTTPException(404, "Evidence not found")
    return FileResponse(str(path), media_type="image/jpeg")


class PaymentIn(BaseModel):
    method: str = "upi"
    simulate_failure: bool = False  # demo a declined payment


@router.post("/challans/{challan_number}/pay")
def pay_challan(challan_number: str, body: PaymentIn, user: dict = Depends(owner_only)):
    from ..enforcement import payments

    try:
        payment = payments.pay(challan_number, user["owner_id"], body.method, user["email"],
                               body.simulate_failure)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except payments.PaymentConflict as exc:
        raise HTTPException(409, str(exc))
    except payments.PaymentError as exc:
        raise HTTPException(422, str(exc))
    if payment["status"] != "success":
        raise HTTPException(402, f"Payment failed: {payment['failure_reason']} "
                                 f"(transaction {payment['transaction_id']})")
    return serialize(payment)


@router.get("/challans/{challan_number}/receipt")
def challan_receipt(challan_number: str, user: dict = Depends(owner_only)):
    from ..enforcement import payments

    try:
        return serialize(payments.receipt(challan_number, user["owner_id"]))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except payments.PaymentError as exc:
        raise HTTPException(409, str(exc))


@router.get("/payments")
def my_payments(user: dict = Depends(owner_only)):
    from ..enforcement import payments

    return serialize(payments.history(user["owner_id"]))


@router.get("/notifications")
def my_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200),
                     user: dict = Depends(owner_only)):
    q = {"owner_id": user["owner_id"]}
    if unread_only:
        q["read"] = False
    return serialize(list(db.notifications.find(q, {"_id": 0, "dedupe_key": 0})
                          .sort("created_at", -1).limit(limit)))


@router.post("/notifications/read-all")
def read_all(user: dict = Depends(owner_only)):
    r = db.notifications.update_many({"owner_id": user["owner_id"], "read": False},
                                     {"$set": {"read": True}})
    return {"updated": r.modified_count}


@router.post("/notifications/{notification_id}/read")
def read_one(notification_id: str, user: dict = Depends(owner_only)):
    r = db.notifications.update_one({"notification_id": notification_id,
                                     "owner_id": user["owner_id"]}, {"$set": {"read": True}})
    if not r.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"updated": r.modified_count}
