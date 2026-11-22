"""Synthetic demonstration owners and vehicles.

All records are fictional and tagged ``demo: True``.  E-mail addresses use the
reserved ``example.com`` domain and phone numbers use the unallocated
``+91 90000 0xxxx`` range, so no real person can be contacted.

``seed()`` also creates a Vehicle Owner login per demo owner
(``owner<N>@example.com`` / ``DEMO_OWNER_PASSWORD``, default ``owner123``).
It is idempotent (upserts by ``owner_id`` / ``registration_number``)
and ``remove()`` deletes only demo-tagged records.
"""
import os
from typing import Dict, List

from .. import db
from .store import now

DEMO_OWNERS: List[dict] = [
    {"owner_id": "DEMO-OWN-001", "name": "Aarav Sharma (Demo)", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"},
    {"owner_id": "DEMO-OWN-002", "name": "Diya Iyer (Demo)", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001"},
    {"owner_id": "DEMO-OWN-003", "name": "Kabir Mehta (Demo)", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
    {"owner_id": "DEMO-OWN-004", "name": "Ananya Reddy (Demo)", "city": "Hyderabad", "state": "Telangana", "pincode": "500001"},
    {"owner_id": "DEMO-OWN-005", "name": "Vihaan Gupta (Demo)", "city": "New Delhi", "state": "Delhi", "pincode": "110001"},
    {"owner_id": "DEMO-OWN-006", "name": "Meera Nair (Demo)", "city": "Kochi", "state": "Kerala", "pincode": "682001"},
    {"owner_id": "DEMO-OWN-007", "name": "Rohan Patel (Demo)", "city": "Ahmedabad", "state": "Gujarat", "pincode": "380001"},
    {"owner_id": "DEMO-OWN-008", "name": "Ishita Verma (Demo)", "city": "Lucknow", "state": "Uttar Pradesh", "pincode": "226001"},
]

# (registration, owner index, make, model, class, colour, fuel)
DEMO_VEHICLES = [
    ("KA01AB1234", 0, "Maruti Suzuki", "Swift", "Car", "White", "Petrol"),
    ("KA05MN2024", 0, "Honda", "Activa 6G", "2-Wheeler", "Grey", "Petrol"),
    ("TN09BX4521", 1, "Hyundai", "Creta", "Car", "Red", "Diesel"),
    ("MH12DE4321", 2, "Tata", "Nexon EV", "Car", "Blue", "Electric"),
    ("MH01CQ7788", 2, "Bajaj", "RE Compact", "3-Wheeler", "Yellow", "CNG"),
    ("TS09EZ1122", 3, "Toyota", "Innova Crysta", "Car", "Silver", "Diesel"),
    ("DL3CAB1234", 4, "Mahindra", "Scorpio-N", "Car", "Black", "Diesel"),
    ("22BH6789C", 4, "Royal Enfield", "Classic 350", "2-Wheeler", "Maroon", "Petrol"),
    ("KL07CD5566", 5, "Kia", "Seltos", "Car", "White", "Petrol"),
    ("GJ01KL3344", 6, "Ashok Leyland", "Dost+", "Truck", "Orange", "Diesel"),
    ("GJ05RT9090", 6, "Maruti Suzuki", "Eeco", "Tempo/Van", "White", "CNG"),
    ("UP32GH6543", 7, "TVS", "Jupiter", "2-Wheeler", "Black", "Petrol"),
    ("UP32MK1010", 7, "Tata", "Punch", "Car", "Orange", "Petrol"),
]


def owner_docs() -> List[dict]:
    out = []
    for i, o in enumerate(DEMO_OWNERS, start=1):
        out.append({
            "owner_id": o["owner_id"],
            "name": o["name"],
            "email": f"owner{i}@example.com",
            "phone": f"+91 90000 0{i:04d}",
            "address": {"line1": f"{10 + i}, Demo Residency", "city": o["city"],
                        "state": o["state"], "pincode": o["pincode"]},
            "demo": True,
        })
    return out


def vehicle_docs() -> List[dict]:
    out = []
    for reg, owner_idx, make, model, cls, colour, fuel in DEMO_VEHICLES:
        out.append({
            "registration_number": reg, "owner_id": DEMO_OWNERS[owner_idx]["owner_id"],
            "make": make, "model": model, "vehicle_class": cls, "colour": colour,
            "fuel_type": fuel, "registered_on": "2021-04-01", "demo": True,
        })
    return out


DEMO_OWNER_PASSWORD = os.getenv("DEMO_OWNER_PASSWORD", "owner123")


def _seed_owner_logins(ts) -> int:
    """One Vehicle Owner login per demo owner (same e-mail as the owner record)."""
    from ..auth import OWNER_ROLE, hash_pw

    created = 0
    for o in owner_docs():
        if db.users.find_one({"email": o["email"]}):
            continue
        db.users.insert_one({"name": o["name"], "email": o["email"], "role": OWNER_ROLE,
                             "owner_id": o["owner_id"], "password": hash_pw(DEMO_OWNER_PASSWORD),
                             "demo": True, "created_at": ts})
        created += 1
    return created


def seed() -> Dict[str, int]:
    created = {"owners": 0, "vehicles": 0}
    ts = now()
    for doc in owner_docs():
        r = db.owners.update_one({"owner_id": doc["owner_id"]},
                                 {"$set": doc, "$setOnInsert": {"created_at": ts}}, upsert=True)
        created["owners"] += int(r.upserted_id is not None)
    for doc in vehicle_docs():
        r = db.vehicles.update_one({"registration_number": doc["registration_number"]},
                                   {"$set": doc, "$setOnInsert": {"created_at": ts}}, upsert=True)
        created["vehicles"] += int(r.upserted_id is not None)
    created["owner_logins"] = _seed_owner_logins(ts)
    return {**created, "total_owners": len(DEMO_OWNERS), "total_vehicles": len(DEMO_VEHICLES)}


def remove() -> Dict[str, int]:
    return {"owner_logins": db.users.delete_many({"demo": True, "role": "Vehicle Owner"}).deleted_count,
            "owners": db.owners.delete_many({"demo": True}).deleted_count,
            "vehicles": db.vehicles.delete_many({"demo": True}).deleted_count}
