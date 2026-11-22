"""Post-detection processing pipeline.

    detected ──ANPR──▶ verified ─────────────▶ (owner lookup, challan)
                 └───▶ pending_review ─manual verify─▶ verified
                                     └─reject────────▶ rejected

Each step is a small function so new violation types / steps can be added
without touching the detectors.
"""
import hashlib
import logging
from typing import List, Optional

from .. import db
from . import challans, plates, registry
from .config import enforcement_settings as es
from .evidence import EvidenceStore
from .store import ViolationStatus as S, add_history, now

log = logging.getLogger("astra.enforcement")
REVIEWABLE = {S.DETECTED, S.PENDING_REVIEW, S.VERIFIED, S.UNREGISTERED}


def evidence_store() -> EvidenceStore:
    return EvidenceStore(es.evidence_dir)


# ------------------------------------------------------------------ plates
def _plate_doc(**kw) -> dict:
    base = {"number": None, "formatted": None, "raw_text": None, "ocr_confidence": None,
            "detector_confidence": None, "confidence": None, "corrections": 0, "format": None,
            "source": None, "engine": None, "review_reasons": [], "candidates": [],
            "verified": False, "verified_by": None, "verified_at": None}
    base.update(kw)
    return base


def run_anpr(doc: dict, anpr_service=None) -> dict:
    """Read the plate from the stored vehicle crops and update the violation."""
    vid = doc["violation_id"]
    store = evidence_store()
    crops = [store.load(p) for p in (doc.get("evidence") or {}).get("vehicle_crops", [])]
    crops = [c for c in crops if c is not None]
    if not es.anpr_enabled:
        return _to_review(doc, ["anpr_disabled"])
    if not crops:
        return _to_review(doc, ["no_vehicle_image"])
    try:
        from . import anpr
        result = (anpr_service or anpr.service()).recognize(crops)
    except Exception as exc:  # model missing, OCR failure ... -> human review, never drop
        log.warning("ANPR failed for %s: %s", vid, exc)
        return _to_review(doc, [f"anpr_unavailable: {exc}"[:200]])

    folder = doc["evidence"]["vehicle_crops"][0].rsplit("/", 1)[0]
    plate_crops = []
    for i, cand in enumerate(result.candidates[:3]):
        if cand.crop is not None and cand.crop.size:
            plate_crops.append(store.save_image(folder, f"plate_{i}.jpg", cand.crop, 95))
    best = result.best
    plate = _plate_doc(
        number=best.number if best else None, formatted=best.formatted if best else None,
        raw_text=best.raw_text if best else None,
        ocr_confidence=best.ocr_confidence if best else None,
        detector_confidence=best.detector_confidence if best else None,
        confidence=best.confidence if best else None, corrections=best.corrections if best else 0,
        format=best.plate_format if best else None, source="anpr", engine=result.engine,
        review_reasons=result.review_reasons,
        candidates=[{"number": c.number, "raw_text": c.raw_text, "confidence": c.confidence,
                     "ocr_confidence": c.ocr_confidence, "detector_confidence": c.detector_confidence}
                    for c in result.candidates[:5]],
        verified=result.auto_verified,
        verified_by="anpr" if result.auto_verified else None,
        verified_at=now() if result.auto_verified else None,
    )
    status = S.VERIFIED if result.auto_verified else S.PENDING_REVIEW
    action = "plate_auto_verified" if result.auto_verified else "plate_needs_review"
    note = (f"{plate['number']} ({plate['confidence']})" if plate["number"]
            else ", ".join(result.review_reasons))
    add_history(vid, "system", action, note, plate=plate, status=status,
                **{"evidence.plate_crops": plate_crops})
    return db.violations.find_one({"violation_id": vid})


def _to_review(doc: dict, reasons: List[str]) -> dict:
    plate = _plate_doc(source="anpr", review_reasons=reasons)
    add_history(doc["violation_id"], "system", "plate_needs_review", ", ".join(reasons),
                plate=plate, status=S.PENDING_REVIEW)
    return db.violations.find_one({"violation_id": doc["violation_id"]})


def simulated_plate(vehicle_id: str, source_id: str) -> str:
    """Deterministic synthetic registration for a SUMO vehicle (no camera exists)."""
    h = hashlib.sha256(f"{source_id}:{vehicle_id}".encode()).digest()
    states = ("KA", "MH", "TN", "DL", "TS", "KL", "GJ", "UP")
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    return (f"{states[h[0] % len(states)]}{1 + h[1] % 70:02d}"
            f"{letters[h[2] % len(letters)]}{letters[h[3] % len(letters)]}"
            f"{int.from_bytes(h[4:6], 'big') % 9000 + 1000}")


def simulation_plate_for(vehicle_id: str, source_id: str) -> str:
    """Map a SUMO vehicle onto a registry vehicle (deterministic).

    ~10 % of vehicles get an unregistered synthetic plate so the
    unknown-registration path is exercised in simulations too.
    """
    h = hashlib.sha256(f"{source_id}:{vehicle_id}:registry".encode()).digest()
    if h[0] % 10:
        regs = sorted(v["registration_number"] for v in
                      db.vehicles.find({"demo": True}, {"registration_number": 1}))
        if regs:
            return regs[int.from_bytes(h[1:3], "big") % len(regs)]
    return simulated_plate(vehicle_id, source_id)


def assign_simulation_plate(doc: dict) -> dict:
    number = simulation_plate_for(doc["track_id"], doc["source"]["source_id"])
    parsed = plates.normalize(number)
    plate = _plate_doc(number=parsed.number, formatted=parsed.formatted, raw_text=number,
                       confidence=1.0, format=parsed.kind, source="simulation",
                       engine="sumo-vehicle-id", verified=True, verified_by="simulation",
                       verified_at=now())
    add_history(doc["violation_id"], "system", "plate_assigned_simulation", parsed.number,
                plate=plate, status=S.VERIFIED)
    return db.violations.find_one({"violation_id": doc["violation_id"]})


# ------------------------------------------------------------ manual review
class ReviewError(ValueError):
    """Invalid input for a review action (HTTP 422)."""


class ReviewConflict(ReviewError):
    """Action not allowed in the violation's current status (HTTP 409)."""


def verify_plate(violation_id: str, number: str, user_email: str, note: Optional[str] = None) -> dict:
    doc = db.violations.find_one({"violation_id": violation_id})
    if not doc:
        raise LookupError("Violation not found")
    if doc["status"] not in REVIEWABLE:
        raise ReviewConflict(f"Cannot verify a violation with status {doc['status']!r}")
    parsed = plates.normalize(number)
    if not parsed:
        raise ReviewError("Not a valid Indian registration number (e.g. KA01AB1234 or 22BH1234AB)")
    old = doc.get("plate") or {}
    plate = _plate_doc(**{k: old.get(k) for k in ("raw_text", "ocr_confidence", "detector_confidence",
                                                  "candidates", "engine")})
    plate.update(number=parsed.number, formatted=parsed.formatted, format=parsed.kind,
                 confidence=1.0, source="manual", verified=True, verified_by=user_email,
                 verified_at=now(), anpr_number=old.get("number"),
                 review_reasons=old.get("review_reasons") or [])
    add_history(violation_id, user_email, "plate_verified_manually",
                f"{parsed.number}" + (f" – {note}" if note else ""), plate=plate, status=S.VERIFIED)
    return process_verified(db.violations.find_one({"violation_id": violation_id}), user_email)


def reject(violation_id: str, user_email: str, reason: str) -> dict:
    doc = db.violations.find_one({"violation_id": violation_id})
    if not doc:
        raise LookupError("Violation not found")
    if doc["status"] not in REVIEWABLE:
        raise ReviewConflict(f"Cannot reject a violation with status {doc['status']!r}")
    add_history(violation_id, user_email, "rejected", reason, status=S.REJECTED,
                rejection_reason=reason)
    return db.violations.find_one({"violation_id": violation_id})


# --------------------------------------------------------------- orchestration
def resolve_owner(doc: dict, user_email: str = "system") -> dict:
    """FR12: match the verified registration with the owner registry."""
    vid, number = doc["violation_id"], (doc.get("plate") or {}).get("number")
    match = registry.lookup(number) if number else None
    if not match:
        add_history(vid, user_email, "registration_not_found", number,
                    status=S.UNREGISTERED, owner=None, vehicle=None, registry_warnings=[])
        return db.violations.find_one({"violation_id": vid})
    warnings = []
    if registry.class_mismatch(match["vehicle"].get("vehicle_class"), doc.get("vehicle_class")):
        warnings.append(f"detected class {doc.get('vehicle_class')!r} differs from registered "
                        f"class {match['vehicle'].get('vehicle_class')!r}")
    add_history(vid, user_email, "owner_matched", match["owner"]["owner_id"], status=S.VERIFIED,
                owner=registry.owner_snapshot(match["owner"]),
                vehicle=registry.vehicle_snapshot(match["vehicle"]), registry_warnings=warnings)
    return db.violations.find_one({"violation_id": vid})


def process_verified(doc: dict, user_email: str) -> dict:
    """Steps after a plate is verified: owner lookup (FR12) → challan (FR13)."""
    doc = resolve_owner(doc, user_email)
    if doc["status"] == S.VERIFIED and doc.get("owner") and es.challan_auto_issue:
        try:
            challans.issue(doc, "system" if user_email == "system" else user_email)
        except challans.ChallanError as exc:
            log.warning("Challan not issued for %s: %s", doc["violation_id"], exc)
            add_history(doc["violation_id"], "system", "challan_not_issued", str(exc))
        doc = db.violations.find_one({"violation_id": doc["violation_id"]})
    return doc


def process_new(docs: List[dict], user_email: str, anpr_service=None) -> List[dict]:
    out = []
    for doc in docs:
        try:
            if doc["source"]["kind"] == "sumo":
                doc = assign_simulation_plate(doc)
            else:
                doc = run_anpr(doc, anpr_service)
            if doc["status"] == S.VERIFIED:
                doc = process_verified(doc, user_email)
        except Exception:  # keep the violation; it stays visible for manual handling
            log.exception("Post-processing failed for %s", doc.get("violation_id"))
            doc = db.violations.find_one({"violation_id": doc["violation_id"]}) or doc
        out.append(doc)
    return out
