"""FR14 – Vehicle Owner role, owner/admin dashboards, notifications, isolation."""
from datetime import timedelta

import pytest

from app import db
from app.enforcement import challans, demo_data
from app.enforcement.store import now
from tests.conftest import auth_header, make_user


def _issue(vid, reg, owner_id, minutes=0):
    owner = db.owners.find_one({"owner_id": owner_id}, {"_id": 0})
    vehicle = db.vehicles.find_one({"registration_number": reg}, {"_id": 0})
    db.violations.insert_one({
        "violation_id": vid, "event_key": vid, "type": "red_light", "status": "verified",
        "occurred_at": now() + timedelta(minutes=minutes),
        "source": {"kind": "video", "source_id": "s"}, "approach": "north", "lane": "north",
        "plate": {"number": reg, "verified": True}, "owner": owner, "vehicle": vehicle,
        "evidence": {}, "history": []})
    return challans.issue(db.violations.find_one({"violation_id": vid}), "test")


@pytest.fixture
def seeded():
    demo_data.seed()
    a = _issue("V1", "KA01AB1234", "DEMO-OWN-001")
    b = _issue("V2", "KA05MN2024", "DEMO-OWN-001", minutes=10)
    c = _issue("V3", "TN09BX4521", "DEMO-OWN-002")
    return a, b, c


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_login_and_role(client, seeded):
    data = login(client, "owner1@example.com", "owner123")
    assert data["user"]["role"] == "Vehicle Owner" and data["user"]["owner_id"] == "DEMO-OWN-001"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200 and me.json()["role"] == "Vehicle Owner"


def test_owner_blocked_from_staff_features(client, seeded):
    h = auth_header("owner1@example.com")
    for method, url in (("get", "/api/detect/history"), ("get", "/api/live-feed/status"),
                        ("get", "/api/simulation/comparison"), ("get", "/api/violations"),
                        ("get", "/api/challans"), ("get", "/api/registry/owners"),
                        ("get", "/api/enforcement/summary"), ("get", "/api/auth/users")):
        assert getattr(client, method)(url, headers=h).status_code == 403, url


def test_staff_blocked_from_owner_portal(client, seeded, operator_headers, admin_headers):
    assert client.get("/api/owner/dashboard", headers=operator_headers).status_code == 403
    assert client.get("/api/owner/dashboard", headers=admin_headers).status_code == 403
    assert client.get("/api/owner/dashboard").status_code == 401


def test_existing_roles_still_work(client, operator_headers, admin_headers):
    assert client.get("/api/detect/history", headers=operator_headers).status_code == 200
    assert client.get("/api/auth/users", headers=admin_headers).status_code == 200
    assert client.get("/api/auth/users", headers=operator_headers).status_code == 403


def test_owner_dashboard_only_own_records(client, seeded):
    a, b, c = seeded
    h = auth_header("owner1@example.com")
    d = client.get("/api/owner/dashboard", headers=h).json()
    assert d["owner"]["owner_id"] == "DEMO-OWN-001"
    assert {v["registration_number"] for v in d["vehicles"]} == {"KA01AB1234", "KA05MN2024"}
    assert d["summary"]["total_challans"] == 2 and d["summary"]["amount_outstanding"] == 2000
    assert d["unread_notifications"] == 2
    lst = client.get("/api/owner/challans", headers=h).json()
    assert {x["challan_number"] for x in lst} == {a["challan_number"], b["challan_number"]}
    assert all("history" not in x and "issued_by" not in x for x in lst)
    # another owner's challan and evidence are invisible
    assert client.get(f"/api/owner/challans/{c['challan_number']}", headers=h).status_code == 404
    assert client.get(f"/api/owner/challans/{c['challan_number']}/evidence/scene",
                      headers=h).status_code == 404
    h2 = auth_header("owner2@example.com")
    assert [x["challan_number"] for x in client.get("/api/owner/challans", headers=h2).json()] \
        == [c["challan_number"]]


def test_owner_evidence_access(client, operator_headers, tmp_path, monkeypatch):
    from app.enforcement import anpr
    from tests.test_fr11_anpr import svc, upload_video

    demo_data.seed()
    monkeypatch.setattr(anpr, "_service", svc([((10, 10, 60, 30), 0.9)],
                                              [("KA01AB1234", 0.97, (0, 0, 50, 20))]))
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    h = auth_header("owner1@example.com")
    n = v["challan_number"]
    r = client.get(f"/api/owner/challans/{n}/evidence/scene", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/owner/challans/{n}/evidence/plate_crops?index=0",
                      headers=h).status_code == 200
    assert client.get(f"/api/owner/challans/{n}/evidence/scene",
                      headers=auth_header("owner2@example.com")).status_code == 404


def test_notifications(client, seeded):
    a, _, _ = seeded
    h = auth_header("owner1@example.com")
    notes = client.get("/api/owner/notifications", headers=h).json()
    assert len(notes) == 2 and all(n["kind"] == "challan_issued" for n in notes)
    assert "₹1000" in notes[0]["message"]
    outbox = list(db.notification_outbox.find({"to": "owner1@example.com"}))
    assert len(outbox) == 2 and all(o["status"] == "simulated" for o in outbox)
    nid = notes[0]["notification_id"]
    other = auth_header("owner2@example.com")
    assert client.post(f"/api/owner/notifications/{nid}/read", headers=other).status_code == 404
    assert client.post(f"/api/owner/notifications/{nid}/read", headers=h).status_code == 200
    assert len(client.get("/api/owner/notifications?unread_only=true", headers=h).json()) == 1
    assert client.post("/api/owner/notifications/read-all", headers=h).json()["updated"] == 1
    # cancellation notifies the owner
    challans.cancel(a["challan_number"], "admin@test.local", "duplicate evidence")
    kinds = [n["kind"] for n in client.get("/api/owner/notifications", headers=h).json()]
    assert "challan_cancelled" in kinds


def test_admin_summary(client, seeded, operator_headers):
    s = client.get("/api/enforcement/summary", headers=operator_headers).json()
    assert s["challans"]["total_challans"] == 3 and s["challans"]["amount_outstanding"] == 3000
    assert s["violations"]["total"] == 3
    assert len(s["daily"]) == 14 and sum(d["challans"] for d in s["daily"]) == 3
    assert s["top_offenders"][0]["challans"] == 1


def test_create_owner_user_requires_owner_record(client, admin_headers):
    demo_data.seed()
    body = {"name": "X", "email": "x@example.com", "password": "pw12345", "role": "Vehicle Owner"}
    assert client.post("/api/auth/users", headers=admin_headers, json=body).status_code == 400
    body["owner_id"] = "DEMO-OWN-001"           # already has a demo login
    assert client.post("/api/auth/users", headers=admin_headers, json=body).status_code == 409
    o = client.post("/api/registry/owners", headers=admin_headers, json={"name": "Y Owner"}).json()
    body["owner_id"] = o["owner_id"]
    r = client.post("/api/auth/users", headers=admin_headers, json=body)
    assert r.status_code == 200 and r.json()["owner_id"] == o["owner_id"]


def test_owner_without_owner_id_rejected(client):
    make_user("Vehicle Owner", "broken@example.com")
    assert client.get("/api/owner/dashboard",
                      headers=auth_header("broken@example.com")).status_code == 403
