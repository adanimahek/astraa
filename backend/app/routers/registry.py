"""Vehicle-owner registry endpoints."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from .. import db
from ..auth import admin_only, current_user
from ..enforcement import demo_data, plates, registry
from ..enforcement.store import serialize

router = APIRouter(prefix="/api/registry", tags=["registry"])


@router.get("/vehicles/{registration_number}")
def lookup_vehicle(registration_number: str, _: dict = Depends(current_user)):
    match = registry.lookup(registration_number)
    if not match:
        raise HTTPException(404, "Registration number not found in the owner registry")
    return serialize(match)


@router.get("/vehicles")
def list_vehicles(q: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                  _: dict = Depends(current_user)):
    query = {}
    if q:
        query = {"registration_number": {"$regex": "^" + re.escape(plates.clean(q))}}
    return [serialize(v) for v in db.vehicles.find(query).sort("registration_number", 1).limit(limit)]


@router.get("/owners")
def list_owners(limit: int = Query(100, ge=1, le=500), _: dict = Depends(current_user)):
    out = []
    for o in db.owners.find().sort("owner_id", 1).limit(limit):
        o["vehicle_count"] = db.vehicles.count_documents({"owner_id": o["owner_id"]})
        out.append(serialize(o))
    return out


class Address(BaseModel):
    line1: str = ""
    city: str = ""
    state: str = ""
    pincode: str = ""


class OwnerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    address: Address = Address()


class VehicleIn(BaseModel):
    registration_number: str
    owner_id: str
    make: str = ""
    model: str = ""
    vehicle_class: str = "Car"
    colour: str = ""
    fuel_type: str = ""


@router.post("/owners")
def create_owner(body: OwnerIn, _: dict = Depends(admin_only)):
    try:
        return serialize(registry.create_owner(body.dict()))
    except DuplicateKeyError:
        raise HTTPException(409, "An owner with this e-mail already exists")


@router.post("/vehicles")
def create_vehicle(body: VehicleIn, _: dict = Depends(admin_only)):
    try:
        return serialize(registry.create_vehicle(body.dict()))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except DuplicateKeyError:
        raise HTTPException(409, "Registration number already exists")


@router.post("/demo/seed")
def seed_demo(_: dict = Depends(admin_only)):
    return demo_data.seed()


@router.delete("/demo")
def remove_demo(_: dict = Depends(admin_only)):
    return demo_data.remove()
