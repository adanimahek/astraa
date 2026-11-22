"""Overdue tracking and **simulated** challan payments.

No real bank or payment gateway is contacted and no card / account details
are collected.  A payment is a database transaction that atomically moves a
challan from ``unpaid`` to ``paid`` and records a transaction ID and receipt.

Overdue:
* ``display_status`` reports ``overdue`` for any unpaid challan past its due
  date (always accurate, even between job runs);
* ``mark_overdue`` (run periodically from ``main.py`` and on demand by an
  administrator) flags newly overdue challans, records history and notifies
  the owner exactly once.
"""
import secrets
from typing import Iterable, Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from .. import db
from . import notifications
from .challans import ChallanStatus
from .store import add_history, as_utc, now

METHODS = {"upi": "UPI (simulated)", "card": "Debit/Credit card (simulated)",
           "netbanking": "Net banking (simulated)"}


class PaymentError(ValueError):
    """Invalid payment request (HTTP 422)."""


class PaymentConflict(PaymentError):
    """Challan cannot be paid in its current state (HTTP 409)."""


def ensure_indexes() -> None:
    db.payments.create_index("transaction_id", unique=True)
    db.payments.create_index("receipt_number", unique=True, sparse=True)
    db.payments.create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
    db.payments.create_index("challan_number")


# ------------------------------------------------------------------- status
def is_overdue(ch: dict, at=None) -> bool:
    return (ch.get("status") == ChallanStatus.UNPAID and ch.get("due_date") is not None
            and as_utc(ch["due_date"]) < (at or now()))


def display_status(ch: dict) -> str:
    return "overdue" if is_overdue(ch) else ch["status"]


def status_filter(status: Optional[str]) -> dict:
    if not status:
        return {}
    if status == "overdue":
        return {"status": ChallanStatus.UNPAID, "due_date": {"$lt": now()}}
    return {"status": status}


def summarize(challans: Iterable[dict]) -> dict:
    out = {"total_challans": 0, "unpaid": 0, "paid": 0, "cancelled": 0, "overdue": 0,
           "amount_outstanding": 0, "amount_paid": 0, "amount_overdue": 0}
    at = now()
    for ch in challans:
        out["total_challans"] += 1
        amount = ch["fine"]["amount"]
        status = ch["status"]
        if status in out:
            out[status] += 1  # "unpaid" includes overdue challans
        if status == ChallanStatus.UNPAID:
            out["amount_outstanding"] += amount
            if is_overdue(ch, at):
                out["overdue"] += 1
                out["amount_overdue"] += amount
        elif status == ChallanStatus.PAID:
            out["amount_paid"] += (ch.get("payment") or {}).get("amount", amount)
    return out


def mark_overdue() -> int:
    """Flag unpaid challans past their due date (idempotent). Returns how many were flagged."""
    at = now()
    flagged = 0
    for ch in db.challans.find({"status": ChallanStatus.UNPAID, "due_date": {"$lt": at},
                                "overdue": {"$ne": True}}):
        res = db.challans.update_one(
            {"_id": ch["_id"], "status": ChallanStatus.UNPAID, "overdue": {"$ne": True}},
            {"$set": {"overdue": True, "overdue_flagged_at": at},
             "$push": {"history": {"at": at, "by": "system", "action": "marked_overdue"}}})
        if not res.modified_count:
            continue
        flagged += 1
        add_history(ch["violation_id"], "system", "challan_overdue", ch["challan_number"])
        notifications.notify(
            ch["owner"], "challan_overdue", f"E-challan {ch['challan_number']} is overdue",
            f"The fine of ₹{ch['fine']['amount']} for {ch['registration_number']} was due on "
            f"{as_utc(ch['due_date']):%d %b %Y} and is now overdue. Please pay it promptly.",
            ch["challan_number"])
    return flagged


# ----------------------------------------------------------------- payments
def _receipt_number(at) -> str:
    counter = db.counters.find_one_and_update(
        {"_id": f"receipt-{at.year}"}, {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER)
    return f"RCPT-{at.year}-{counter['seq']:07d}"


def _transaction_id(at) -> str:
    return f"SIMTXN{at:%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}"


def pay(challan_number: str, owner_id: str, method: str, paid_by: str,
        simulate_failure: bool = False) -> dict:
    """Simulate paying an owner's challan.  Returns the payment record."""
    if method not in METHODS:
        raise PaymentError(f"method must be one of {sorted(METHODS)}")
    ch = db.challans.find_one({"challan_number": challan_number, "owner_id": owner_id})
    if not ch:
        raise LookupError("Challan not found")
    if ch["status"] != ChallanStatus.UNPAID:
        raise PaymentConflict(f"Challan is already {ch['status']}")
    at = now()
    base = {"transaction_id": _transaction_id(at), "challan_number": challan_number,
            "owner_id": owner_id, "registration_number": ch["registration_number"],
            "amount": ch["fine"]["amount"], "currency": ch["fine"].get("currency", "INR"),
            "method": method, "method_label": METHODS[method], "paid_by": paid_by,
            "simulated": True, "was_overdue": is_overdue(ch, at), "created_at": at}

    if simulate_failure:  # demo of a declined payment; challan stays unpaid
        failed = {**base, "status": "failed", "failure_reason": "Simulated decline (demo)"}
        db.payments.insert_one(failed)
        failed.pop("_id", None)
        return failed

    payment = {**base, "status": "success", "receipt_number": _receipt_number(at), "paid_at": at}
    updated = db.challans.find_one_and_update(  # atomic: prevents double payment
        {"_id": ch["_id"], "status": ChallanStatus.UNPAID},
        {"$set": {"status": ChallanStatus.PAID,
                  "payment": {k: payment[k] for k in ("transaction_id", "receipt_number", "amount",
                                                      "currency", "method", "paid_at",
                                                      "was_overdue", "simulated")}},
         "$push": {"history": {"at": at, "by": paid_by, "action": "paid",
                               "note": payment["transaction_id"]}}},
        return_document=ReturnDocument.AFTER)
    if updated is None:
        raise PaymentConflict("Challan was paid or cancelled by another request")
    db.payments.insert_one(payment)
    payment.pop("_id", None)
    add_history(ch["violation_id"], paid_by, "challan_paid", payment["transaction_id"])
    notifications.notify(
        ch["owner"], "payment_received", f"Payment received for {challan_number}",
        f"₹{payment['amount']} received via {METHODS[method]}. Transaction {payment['transaction_id']}, "
        f"receipt {payment['receipt_number']}.", challan_number)
    return payment


def receipt(challan_number: str, owner_id: Optional[str] = None) -> dict:
    q = {"challan_number": challan_number}
    if owner_id is not None:
        q["owner_id"] = owner_id
    ch = db.challans.find_one(q)
    if not ch:
        raise LookupError("Challan not found")
    if ch["status"] != ChallanStatus.PAID or not ch.get("payment"):
        raise PaymentConflict("No receipt: challan is not paid")
    p = ch["payment"]
    return {
        "receipt_number": p["receipt_number"], "transaction_id": p["transaction_id"],
        "paid_at": p["paid_at"], "amount": p["amount"], "currency": p.get("currency", "INR"),
        "method": METHODS.get(p["method"], p["method"]), "was_overdue": p.get("was_overdue", False),
        "challan_number": ch["challan_number"], "violation": ch["violation_label"],
        "legal_section": ch["legal_section"], "occurred_at": ch["occurred_at"],
        "issued_at": ch["issued_at"], "due_date": ch["due_date"],
        "registration_number": ch["registration_number"],
        "owner": {k: (ch.get("owner") or {}).get(k) for k in ("owner_id", "name")},
        "simulated": True,
        "disclaimer": "Simulated payment for demonstration – no money was transferred.",
    }


def history(owner_id: Optional[str] = None, limit: int = 100) -> list:
    q = {} if owner_id is None else {"owner_id": owner_id}
    return list(db.payments.find(q, {"_id": 0}).sort("created_at", -1).limit(limit))


def payment_summary() -> dict:
    out = {"count": 0, "failed": 0, "total_collected": 0, "by_method": {}, "overdue_payments": 0}
    for p in db.payments.find({}, {"status": 1, "amount": 1, "method": 1, "was_overdue": 1}):
        if p["status"] != "success":
            out["failed"] += 1
            continue
        out["count"] += 1
        out["total_collected"] += p["amount"]
        out["by_method"][p["method"]] = out["by_method"].get(p["method"], 0) + p["amount"]
        out["overdue_payments"] += int(bool(p.get("was_overdue")))
    return out
