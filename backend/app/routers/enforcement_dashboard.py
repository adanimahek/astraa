"""Admin / operator e-challan dashboard summaries."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from .. import db
from ..auth import current_user
from ..enforcement import payments
from ..enforcement.store import as_utc, now, serialize

router = APIRouter(prefix="/api/enforcement", tags=["enforcement dashboard"])


@router.get("/summary")
def summary(days: int = Query(14, ge=1, le=90), _: dict = Depends(current_user)):
    violations_by_status, violations_by_type = {}, {}
    for v in db.violations.find({}, {"status": 1, "type": 1}):
        violations_by_status[v["status"]] = violations_by_status.get(v["status"], 0) + 1
        violations_by_type[v["type"]] = violations_by_type.get(v["type"], 0) + 1

    start = (now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = {(start + timedelta(days=i)).date().isoformat(): {"violations": 0, "challans": 0}
             for i in range(days)}
    for v in db.violations.find({"created_at": {"$gte": start}}, {"created_at": 1}):
        key = as_utc(v["created_at"]).date().isoformat()
        if key in daily:
            daily[key]["violations"] += 1

    all_challans = list(db.challans.find({}, {"history": 0, "evidence": 0}))
    offenders = {}
    for ch in all_challans:
        key = as_utc(ch["issued_at"]).date().isoformat()
        if key in daily:
            daily[key]["challans"] += 1
        if ch["status"] != "cancelled":
            offenders[ch["registration_number"]] = offenders.get(ch["registration_number"], 0) + 1

    recent_violations = db.violations.find({}, {"history": 0, "meta": 0}) \
        .sort("created_at", -1).limit(10)
    return {
        "violations": {"total": sum(violations_by_status.values()), "by_status": violations_by_status,
                       "by_type": violations_by_type,
                       "pending_review": violations_by_status.get("pending_review", 0),
                       "unregistered": violations_by_status.get("unregistered", 0)},
        "challans": payments.summarize(all_challans),
        "payments": payments.payment_summary(),
        "daily": [{"date": d, **v} for d, v in daily.items()],
        "top_offenders": [{"registration_number": k, "challans": n} for k, n in
                          sorted(offenders.items(), key=lambda kv: -kv[1])[:5]],
        "recent_violations": [serialize(v) for v in recent_violations],
    }
