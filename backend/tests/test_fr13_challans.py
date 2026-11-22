"""FR13 – automatic challan generation."""
from datetime import timedelta

import pytest

from app import db
from app.enforcement import challans, demo_data, fines
from app.enforcement.store import as_utc
from tests.test_fr11_anpr import upload_video


@pytest.fixture
def anpr_reads(monkeypatch):
    from app.enforcement import anpr
    from tests.test_fr11_anpr import svc

    def install(number, conf=0.97):
        monkeypatch.setattr(anpr, "_service",
                            svc([((10, 10, 60, 30), 0.9)], [(number, conf, (0, 0, 50, 20))]))
    return install


def test_auto_issue_for_verified_owner_matched(client, operator_headers, tmp_path, monkeypatch,
                                                anpr_reads):
    demo_data.seed()
    anpr_reads("KA01AB1234")
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["status"] == "challan_issued" and v["challan_number"].startswith("ECH-")
    ch = client.get(f"/api/challans/{v['challan_number']}", headers=operator_headers).json()
    assert ch["violation_id"] == v["violation_id"]
    assert ch["registration_number"] == "KA01AB1234" and ch["owner_id"] == "DEMO-OWN-001"
    assert ch["fine"]["amount"] == 1000 and ch["fine"]["currency"] == "INR"
    assert ch["status"] == "unpaid" and ch["payment"] is None
    assert ch["evidence"]["scene"] and ch["vehicle"]["make"] == "Maruti Suzuki"
    issued, due = ch["issued_at"], ch["due_date"]
    from datetime import datetime
    delta = datetime.fromisoformat(due) - datetime.fromisoformat(issued)
    assert delta == timedelta(days=30)


def test_no_challan_without_owner_or_verification(client, operator_headers, tmp_path, monkeypatch,
                                                   anpr_reads):
    anpr_reads("KA02CD4567")                    # unknown registration
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["status"] == "unregistered" and db.challans.count_documents({}) == 0
    r = client.post(f"/api/challans/issue/{v['violation_id']}", headers=operator_headers)
    assert r.status_code == 409


def test_manual_verification_issues_challan(client, operator_headers, tmp_path, monkeypatch,
                                            anpr_reads):
    demo_data.seed()
    anpr_reads("MH12DE4321", conf=0.4)          # uncertain -> review
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["status"] == "pending_review" and db.challans.count_documents({}) == 0
    r = client.post(f"/api/violations/{v['violation_id']}/verify-plate", headers=operator_headers,
                    json={"plate_number": "MH12DE4321"})
    assert r.json()["status"] == "challan_issued"
    assert db.challans.count_documents({"registration_number": "MH12DE4321"}) == 1


def _violation(vid, reg, minutes):
    from app.enforcement.store import now
    return {"violation_id": vid, "event_key": vid, "type": "red_light", "status": "verified",
            "occurred_at": now() + timedelta(minutes=minutes),
            "source": {"kind": "video", "source_id": "s"}, "approach": "north", "lane": "north",
            "plate": {"number": reg, "verified": True},
            "owner": {"owner_id": "DEMO-OWN-001", "name": "x"}, "vehicle": None, "evidence": {}}


def test_duplicates_and_repeat_offence_and_unique_numbers():
    for doc in (_violation("V1", "KA01AB1234", 0), _violation("V2", "KA01AB1234", 1),
                _violation("V3", "KA01AB1234", 30), _violation("V4", "TN09BX4521", 0)):
        db.violations.insert_one(doc)
    c1 = challans.issue(db.violations.find_one({"violation_id": "V1"}), "t")
    assert challans.issue(db.violations.find_one({"violation_id": "V1"}), "t")["challan_number"] \
        == c1["challan_number"]                                  # same violation -> same challan
    c2 = challans.issue(db.violations.find_one({"violation_id": "V2"}), "t")
    assert c2["challan_number"] == c1["challan_number"]          # same vehicle within window
    assert db.violations.find_one({"violation_id": "V2"})["duplicate_of"] == c1["challan_number"]
    c3 = challans.issue(db.violations.find_one({"violation_id": "V3"}), "t")
    c4 = challans.issue(db.violations.find_one({"violation_id": "V4"}), "t")
    numbers = {c1["challan_number"], c3["challan_number"], c4["challan_number"]}
    assert len(numbers) == 3 and db.challans.count_documents({}) == 3
    assert c3["fine"]["repeat_offence"] and c3["fine"]["amount"] == 5000
    assert not c4["fine"]["repeat_offence"] and c4["fine"]["amount"] == 1000


def test_fine_amounts_configurable(client, admin_headers, operator_headers):
    r = client.put("/api/challans/config/fines/red_light", headers=operator_headers,
                   json={"amount": 2000})
    assert r.status_code == 403
    r = client.put("/api/challans/config/fines/red_light", headers=admin_headers,
                   json={"amount": 2500, "due_days": 15})
    assert r.status_code == 200 and r.json()["amount"] == 2500 and r.json()["version"] == 2
    assert client.put("/api/challans/config/fines/red_light", headers=admin_headers,
                      json={"amount": -5}).status_code == 422
    assert client.put("/api/challans/config/fines/speeding", headers=admin_headers,
                      json={"amount": 5}).status_code == 404
    db.violations.insert_one(_violation("V9", "GJ01KL3344", 0))
    ch = challans.issue(db.violations.find_one({"violation_id": "V9"}), "t")
    assert ch["fine"]["amount"] == 2500 and ch["fine"]["rule_version"] == 2
    assert as_utc(ch["due_date"]) - as_utc(ch["issued_at"]) == timedelta(days=15)
    fines_list = client.get("/api/challans/config/fines", headers=operator_headers).json()
    assert fines_list[0]["violation_type"] == "red_light"


def test_cancel_challan(client, admin_headers, operator_headers):
    db.violations.insert_one(_violation("V1", "KA01AB1234", 0))
    ch = challans.issue(db.violations.find_one({"violation_id": "V1"}), "t")
    n = ch["challan_number"]
    assert client.post(f"/api/challans/{n}/cancel", headers=operator_headers,
                       json={"reason": "wrong plate"}).status_code == 403
    r = client.post(f"/api/challans/{n}/cancel", headers=admin_headers, json={"reason": "wrong plate"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.post(f"/api/challans/{n}/cancel", headers=admin_headers,
                       json={"reason": "again"}).status_code == 409
    lst = client.get("/api/challans?q=KA01", headers=operator_headers).json()
    assert lst["total"] == 1


def test_sumo_violations_get_challans(client, operator_headers):
    import shutil
    pytest.importorskip("traci")
    if not shutil.which("sumo"):
        pytest.skip("sumo binary not on PATH")
    demo_data.seed()
    r = client.post("/api/violations/detect/sumo", headers=operator_headers,
                    json={"seed": 101, "duration_seconds": 600, "violation_probability": 0.15})
    assert r.status_code == 200, r.text
    statuses = {v["status"] for v in r.json()["violations"]}
    assert "challan_issued" in statuses
    assert statuses <= {"challan_issued", "unregistered"}
