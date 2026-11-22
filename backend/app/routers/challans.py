"""E-challan endpoints (staff)."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from ..auth import admin_only, current_user
from ..enforcement import challans, fines, payments, plates
from ..enforcement.store import serialize

router = APIRouter(prefix="/api/challans", tags=["challans"])


def challan_query(status: Optional[str] = None, q: Optional[str] = None) -> dict:
    query = dict(payments.status_filter(status))
    if q:
        query["$or"] = [{"registration_number": {"$regex": "^" + re.escape(plates.clean(q))}},
                        {"challan_number": q.strip().upper()}]
    return query


def public_challan(doc: dict) -> dict:
    out = serialize(doc)
    out["display_status"] = payments.display_status(doc)
    return out


@router.get("/config/fines")
def get_fines(_: dict = Depends(current_user)):
    return [serialize({**r, "violation_type": r["_id"]}) for r in fines.list_rules()]


class FineUpdate(BaseModel):
    amount: Optional[int] = Field(None, gt=0, le=1_000_000)
    repeat_amount: Optional[int] = Field(None, gt=0, le=1_000_000)
    due_days: Optional[int] = Field(None, ge=1, le=365)
    legal_section: Optional[str] = Field(None, max_length=300)
    label: Optional[str] = Field(None, max_length=200)
    active: Optional[bool] = None


@router.put("/config/fines/{violation_type}")
def update_fine(violation_type: str, body: FineUpdate, user: dict = Depends(admin_only)):
    try:
        rule = fines.update_rule(violation_type, body.dict(), user["email"])
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return serialize({**rule, "violation_type": rule["_id"]})


@router.get("/payments/history")
def payment_history(limit: int = Query(100, ge=1, le=500), _: dict = Depends(current_user)):
    return serialize(payments.history(limit=limit))


@router.post("/overdue/run")
def run_overdue_check(_: dict = Depends(admin_only)):
    return {"flagged": payments.mark_overdue()}


@router.get("/{challan_number}/receipt")
def staff_receipt(challan_number: str, _: dict = Depends(current_user)):
    try:
        return serialize(payments.receipt(challan_number))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except payments.PaymentError as exc:
        raise HTTPException(409, str(exc))


@router.post("/issue/{violation_id}")
def issue_challan(violation_id: str, user: dict = Depends(current_user)):
    violation = db.violations.find_one({"violation_id": violation_id})
    if not violation:
        raise HTTPException(404, "Violation not found")
    try:
        return public_challan(challans.issue(violation, user["email"]))
    except challans.ChallanError as exc:
        raise HTTPException(409, str(exc))


@router.get("")
def list_challans(status: Optional[str] = None, q: Optional[str] = None,
                  limit: int = Query(50, ge=1, le=500), skip: int = Query(0, ge=0),
                  _: dict = Depends(current_user)):
    query = challan_query(status, q)
    cursor = db.challans.find(query, {"history": 0}).sort("issued_at", -1).skip(skip).limit(limit)
    return {"total": db.challans.count_documents(query),
            "items": [public_challan(c) for c in cursor]}


@router.get("/{challan_number}")
def get_challan(challan_number: str, _: dict = Depends(current_user)):
    doc = db.challans.find_one({"challan_number": challan_number})
    if not doc:
        raise HTTPException(404, "Challan not found")
    return public_challan(doc)


class Cancellation(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/{challan_number}/cancel")
def cancel_challan(challan_number: str, body: Cancellation, user: dict = Depends(admin_only)):
    try:
        return public_challan(challans.cancel(challan_number, user["email"], body.reason))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except challans.ChallanError as exc:
        raise HTTPException(409, str(exc))
