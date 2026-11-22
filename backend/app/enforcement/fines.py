"""Violation types and configurable fine rules.

Add a new violation type by adding an entry to ``VIOLATION_TYPES``; its fine
rule is created automatically from ``CHALLAN_FINE_AMOUNTS`` (env, JSON) or
the default below, and administrators can change it at runtime via
``PUT /api/challans/config/fines/{type}`` (stored in ``fine_rules``).

Amounts are demonstration values and not legal advice; set them to match the
notified fines of the relevant state.
"""
from typing import Dict, Optional

from .. import db
from .config import enforcement_settings as es
from .store import now

VIOLATION_TYPES: Dict[str, dict] = {
    "red_light": {
        "label": "Red-light violation (jumping a traffic signal)",
        "legal_section": "Motor Vehicles Act, 1988 – s.119 r/w s.184 (configurable)",
        "default_amount": 1000,
        "default_repeat_amount": 5000,
    },
}


def _default_rule(vtype: str) -> dict:
    meta = VIOLATION_TYPES[vtype]
    return {
        "_id": vtype,
        "violation_type": vtype,
        "label": meta["label"],
        "legal_section": meta["legal_section"],
        "amount": int(es.default_fines.get(vtype, meta["default_amount"])),
        "repeat_amount": meta.get("default_repeat_amount"),
        "currency": "INR",
        "due_days": es.challan_due_days,
        "active": True,
        "version": 1,
    }


def ensure_rules() -> None:
    for vtype in VIOLATION_TYPES:
        rule = _default_rule(vtype)
        db.fine_rules.update_one({"_id": vtype}, {"$setOnInsert": {**rule, "updated_at": now(),
                                                                  "updated_by": "system"}},
                                 upsert=True)


def get_rule(vtype: str) -> Optional[dict]:
    if vtype not in VIOLATION_TYPES:
        return None
    rule = db.fine_rules.find_one({"_id": vtype})
    if rule is None:
        ensure_rules()
        rule = db.fine_rules.find_one({"_id": vtype})
    return rule


def list_rules() -> list:
    ensure_rules()
    return list(db.fine_rules.find().sort("_id", 1))


def update_rule(vtype: str, changes: dict, by: str) -> dict:
    if vtype not in VIOLATION_TYPES:
        raise LookupError(f"Unknown violation type {vtype!r}")
    ensure_rules()
    allowed = {k: v for k, v in changes.items()
               if k in ("amount", "repeat_amount", "due_days", "legal_section", "label", "active")
               and v is not None}
    if "amount" in allowed and allowed["amount"] <= 0:
        raise ValueError("amount must be positive")
    if "due_days" in allowed and not 1 <= allowed["due_days"] <= 365:
        raise ValueError("due_days must be between 1 and 365")
    db.fine_rules.update_one({"_id": vtype}, {"$set": {**allowed, "updated_at": now(),
                                                       "updated_by": by},
                                              "$inc": {"version": 1}})
    return db.fine_rules.find_one({"_id": vtype})
