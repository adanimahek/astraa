"""Vehicle-owner registry (MongoDB ``vehicle_owners`` / ``vehicles``)."""
from typing import Optional

from pymongo import ASCENDING

from .. import db
from . import plates
from .store import now


def ensure_indexes() -> None:
    db.owners.create_index("owner_id", unique=True)
    db.owners.create_index("email", unique=True, sparse=True)
    db.vehicles.create_index("registration_number", unique=True)
    db.vehicles.create_index([("owner_id", ASCENDING)])


def canonical(number: str) -> Optional[str]:
    parsed = plates.normalize(number)
    return parsed.number if parsed and parsed.corrections == 0 else None


def lookup(number: str) -> Optional[dict]:
    """``{"vehicle": ..., "owner": ...}`` for a registration number, else ``None``."""
    reg = canonical(number) or plates.clean(number)
    vehicle = db.vehicles.find_one({"registration_number": reg}, {"_id": 0})
    if not vehicle:
        return None
    owner = db.owners.find_one({"owner_id": vehicle["owner_id"]}, {"_id": 0})
    if not owner:
        return None
    return {"vehicle": vehicle, "owner": owner}


# Detector classes that are compatible with each registered vehicle class.
_COMPATIBLE = {
    "Car": {"Car", "Tempo/Van"}, "Tempo/Van": {"Car", "Tempo/Van", "Truck"},
    "Bus": {"Bus", "Truck"}, "Truck": {"Truck", "Bus", "Tempo/Van"},
    "2-Wheeler": {"2-Wheeler", "Bicycle"}, "3-Wheeler": {"3-Wheeler", "Tempo/Van"},
}


def class_mismatch(registered: Optional[str], detected: Optional[str]) -> bool:
    if not registered or not detected or registered not in _COMPATIBLE:
        return False
    return detected not in _COMPATIBLE[registered]


def owner_snapshot(owner: dict) -> dict:
    return {k: owner.get(k) for k in ("owner_id", "name", "email", "phone", "address")}


def vehicle_snapshot(vehicle: dict) -> dict:
    return {k: vehicle.get(k) for k in ("registration_number", "make", "model", "vehicle_class",
                                        "colour", "fuel_type", "owner_id")}


def create_owner(data: dict) -> dict:
    count = db.owners.count_documents({})
    owner_id = data.get("owner_id") or f"OWN-{count + 1:05d}"
    while db.owners.find_one({"owner_id": owner_id}):
        count += 1
        owner_id = f"OWN-{count + 1:05d}"
    doc = {**data, "owner_id": owner_id, "email": (data.get("email") or "").lower() or None,
           "created_at": now()}
    if doc["email"] is None:
        doc.pop("email")
    db.owners.insert_one(doc)
    doc.pop("_id", None)
    return doc


def create_vehicle(data: dict) -> dict:
    reg = canonical(data["registration_number"])
    if not reg:
        raise ValueError("Not a valid Indian registration number")
    if not db.owners.find_one({"owner_id": data["owner_id"]}):
        raise LookupError("Owner not found")
    doc = {**data, "registration_number": reg, "created_at": now()}
    db.vehicles.insert_one(doc)
    doc.pop("_id", None)
    return doc
