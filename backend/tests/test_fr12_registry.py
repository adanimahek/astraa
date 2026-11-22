"""FR12 – vehicle-owner lookup and synthetic demo data."""
import pytest

from app import db
from app.enforcement import demo_data, pipeline, plates, registry
from tests.test_fr11_anpr import upload_video


def test_demo_data_is_valid_and_idempotent():
    for v in demo_data.vehicle_docs():
        assert plates.is_valid(v["registration_number"]), v["registration_number"]
    for o in demo_data.owner_docs():
        assert o["email"].endswith("@example.com") and o["demo"] is True
    first = demo_data.seed()
    assert first["owners"] == len(demo_data.DEMO_OWNERS)
    assert first["vehicles"] == len(demo_data.DEMO_VEHICLES)
    again = demo_data.seed()
    assert again["owners"] == 0 and again["vehicles"] == 0
    assert db.vehicles.count_documents({}) == len(demo_data.DEMO_VEHICLES)


def test_remove_only_touches_demo_records():
    demo_data.seed()
    real = registry.create_owner({"name": "Real Person", "email": "Real@Mail.test"})
    registry.create_vehicle({"registration_number": "KA 03 XY 0001", "owner_id": real["owner_id"],
                             "vehicle_class": "Car"})
    demo_data.remove()
    assert db.owners.count_documents({}) == 1 and db.vehicles.count_documents({}) == 1
    assert registry.lookup("ka03xy0001")["owner"]["email"] == "real@mail.test"


def test_lookup_known_unknown_and_formatting():
    demo_data.seed()
    m = registry.lookup("ka 01 ab 1234")
    assert m["vehicle"]["registration_number"] == "KA01AB1234"
    assert m["owner"]["owner_id"] == "DEMO-OWN-001"
    assert registry.lookup("KA01ZZ9999") is None
    assert registry.lookup("garbage") is None


def test_create_vehicle_validation():
    with pytest.raises(ValueError):
        registry.create_vehicle({"registration_number": "NOPE", "owner_id": "x"})
    with pytest.raises(LookupError):
        registry.create_vehicle({"registration_number": "KA01AB1111", "owner_id": "missing"})


def test_class_mismatch():
    assert registry.class_mismatch("2-Wheeler", "Bus")
    assert not registry.class_mismatch("Car", "Tempo/Van")
    assert not registry.class_mismatch(None, "Car")


@pytest.fixture
def anpr_reads(monkeypatch):
    from app.enforcement import anpr
    from tests.test_fr11_anpr import svc

    def install(number, conf=0.97):
        monkeypatch.setattr(anpr, "_service",
                            svc([((10, 10, 60, 30), 0.9)], [(number, conf, (0, 0, 50, 20))]))
    return install


def test_pipeline_matches_owner(client, operator_headers, tmp_path, monkeypatch, anpr_reads):
    demo_data.seed()
    anpr_reads("KA01AB1234")
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["owner"]["owner_id"] == "DEMO-OWN-001"
    assert v["vehicle"]["registration_number"] == "KA01AB1234"
    assert v["registry_warnings"] == []


def test_unknown_registration_then_resolved(client, operator_headers, admin_headers, tmp_path,
                                            monkeypatch, anpr_reads):
    anpr_reads("KA02CD4567")
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    vid = v["violation_id"]
    assert v["status"] == "unregistered" and v["owner"] is None
    listed = client.get("/api/violations?status=unregistered", headers=operator_headers).json()
    assert listed["total"] == 1

    # admin registers the vehicle, operator re-runs lookup
    o = client.post("/api/registry/owners", headers=admin_headers,
                    json={"name": "New Owner", "email": "new.owner@example.com"}).json()
    r = client.post("/api/registry/vehicles", headers=admin_headers,
                    json={"registration_number": "KA02CD4567", "owner_id": o["owner_id"],
                          "vehicle_class": "Car"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/violations/{vid}/resolve-owner", headers=operator_headers)
    assert r.status_code == 200 and r.json()["owner"]["owner_id"] == o["owner_id"]


def test_registry_api_permissions(client, operator_headers, admin_headers):
    assert client.post("/api/registry/demo/seed", headers=operator_headers).status_code == 403
    assert client.post("/api/registry/demo/seed", headers=admin_headers).status_code == 200
    r = client.get("/api/registry/vehicles/MH12DE4321", headers=operator_headers)
    assert r.status_code == 200 and r.json()["owner"]["name"].endswith("(Demo)")
    assert client.get("/api/registry/vehicles/MH12DE0000",
                      headers=operator_headers).status_code == 404
    assert len(client.get("/api/registry/vehicles?q=UP32", headers=operator_headers).json()) == 2
    assert client.get("/api/registry/owners").status_code == 401


def test_simulation_plates_map_to_registry():
    demo_data.seed()
    regs = {v["registration_number"] for v in demo_data.vehicle_docs()}
    picks = [pipeline.simulation_plate_for(f"veh{i}", "sumo-seed1") for i in range(200)]
    in_registry = sum(p in regs for p in picks)
    assert 150 < in_registry < 200          # ~90 % registered, some unknown
    assert all(plates.is_valid(p) for p in picks)
