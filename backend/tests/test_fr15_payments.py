"""FR15 – overdue detection and simulated payments, receipts, history."""
from datetime import timedelta

import pytest

from app import db
from app.enforcement import payments
from app.enforcement.store import now
from tests.conftest import auth_header
from tests.test_fr14_owner_portal import _issue, seeded  # noqa: F401  (fixture)


def _make_overdue(challan_number, days=3):
    db.challans.update_one({"challan_number": challan_number},
                           {"$set": {"due_date": now() - timedelta(days=days)}})


def test_overdue_display_and_filter(client, seeded, operator_headers):
    a, b, c = seeded
    _make_overdue(a["challan_number"])
    h = auth_header("owner1@example.com")
    lst = {x["challan_number"]: x for x in client.get("/api/owner/challans", headers=h).json()}
    assert lst[a["challan_number"]]["display_status"] == "overdue"
    assert lst[a["challan_number"]]["is_overdue"] is True
    assert lst[b["challan_number"]]["display_status"] == "unpaid"
    od = client.get("/api/owner/challans?status=overdue", headers=h).json()
    assert [x["challan_number"] for x in od] == [a["challan_number"]]
    d = client.get("/api/owner/dashboard", headers=h).json()["summary"]
    assert d["overdue"] == 1 and d["amount_overdue"] == 1000 and d["unpaid"] == 2
    staff = client.get("/api/challans?status=overdue", headers=operator_headers).json()
    assert staff["total"] == 1 and staff["items"][0]["display_status"] == "overdue"


def test_mark_overdue_job_idempotent_and_notifies(client, seeded, admin_headers, operator_headers):
    a, b, _ = seeded
    _make_overdue(a["challan_number"])
    assert payments.mark_overdue() == 1
    assert payments.mark_overdue() == 0                        # already flagged
    ch = db.challans.find_one({"challan_number": a["challan_number"]})
    assert ch["overdue"] is True and ch["history"][-1]["action"] == "marked_overdue"
    assert db.notifications.count_documents({"kind": "challan_overdue",
                                             "challan_number": a["challan_number"]}) == 1
    v = db.violations.find_one({"violation_id": ch["violation_id"]})
    assert v["history"][-1]["action"] == "challan_overdue"
    assert client.post("/api/challans/overdue/run", headers=operator_headers).status_code == 403
    _make_overdue(b["challan_number"])
    assert client.post("/api/challans/overdue/run", headers=admin_headers).json() == {"flagged": 1}


def test_simulated_payment_flow(client, seeded, operator_headers):
    a, _, c = seeded
    _make_overdue(a["challan_number"])
    h = auth_header("owner1@example.com")
    n = a["challan_number"]
    assert client.get(f"/api/owner/challans/{n}/receipt", headers=h).status_code == 409
    r = client.post(f"/api/owner/challans/{n}/pay", headers=h, json={"method": "upi"})
    assert r.status_code == 200, r.text
    pay = r.json()
    assert pay["status"] == "success" and pay["simulated"] is True and pay["was_overdue"] is True
    assert pay["transaction_id"].startswith("SIMTXN") and pay["receipt_number"].startswith("RCPT-")
    assert pay["amount"] == 1000

    ch = client.get(f"/api/owner/challans/{n}", headers=h).json()
    assert ch["status"] == "paid" and ch["display_status"] == "paid"
    assert ch["payment"]["transaction_id"] == pay["transaction_id"]
    rc = client.get(f"/api/owner/challans/{n}/receipt", headers=h).json()
    assert rc["receipt_number"] == pay["receipt_number"] and "Simulated" in rc["disclaimer"]
    assert rc["registration_number"] == "KA01AB1234"
    assert client.get(f"/api/challans/{n}/receipt", headers=operator_headers).status_code == 200

    # no double payment, no paying someone else's challan, overdue no longer reported
    assert client.post(f"/api/owner/challans/{n}/pay", headers=h,
                       json={"method": "upi"}).status_code == 409
    assert client.post(f"/api/owner/challans/{c['challan_number']}/pay", headers=h,
                       json={"method": "upi"}).status_code == 404
    assert payments.mark_overdue() == 0
    hist = client.get("/api/owner/payments", headers=h).json()
    assert [p["transaction_id"] for p in hist] == [pay["transaction_id"]]
    kinds = [x["kind"] for x in client.get("/api/owner/notifications", headers=h).json()]
    assert "payment_received" in kinds
    v = db.violations.find_one({"violation_id": a["violation_id"]})
    assert v["history"][-1]["action"] == "challan_paid"


def test_failed_payment_and_validation(client, seeded):
    a, _, _ = seeded
    h = auth_header("owner1@example.com")
    n = a["challan_number"]
    r = client.post(f"/api/owner/challans/{n}/pay", headers=h,
                    json={"method": "card", "simulate_failure": True})
    assert r.status_code == 402
    assert db.challans.find_one({"challan_number": n})["status"] == "unpaid"
    hist = client.get("/api/owner/payments", headers=h).json()
    assert hist[0]["status"] == "failed" and "receipt_number" not in hist[0]
    assert client.post(f"/api/owner/challans/{n}/pay", headers=h,
                       json={"method": "bitcoin"}).status_code == 422
    assert client.post(f"/api/owner/challans/{n}/pay", headers=h,
                       json={"method": "netbanking"}).status_code == 200


def test_cancelled_challan_cannot_be_paid(client, seeded, admin_headers):
    a, _, _ = seeded
    n = a["challan_number"]
    client.post(f"/api/challans/{n}/cancel", headers=admin_headers, json={"reason": "test"})
    r = client.post(f"/api/owner/challans/{n}/pay", headers=auth_header("owner1@example.com"),
                    json={"method": "upi"})
    assert r.status_code == 409


def test_unique_receipts_and_admin_payment_summary(client, seeded, operator_headers):
    a, b, c = seeded
    _make_overdue(b["challan_number"])
    r1 = payments.pay(a["challan_number"], "DEMO-OWN-001", "upi", "t")
    r2 = payments.pay(b["challan_number"], "DEMO-OWN-001", "card", "t")
    r3 = payments.pay(c["challan_number"], "DEMO-OWN-002", "upi", "t")
    assert len({r1["receipt_number"], r2["receipt_number"], r3["receipt_number"]}) == 3
    assert len({r1["transaction_id"], r2["transaction_id"], r3["transaction_id"]}) == 3
    s = client.get("/api/enforcement/summary", headers=operator_headers).json()
    assert s["payments"]["count"] == 3 and s["payments"]["total_collected"] == 3000
    assert s["payments"]["by_method"] == {"upi": 2000, "card": 1000}
    assert s["payments"]["overdue_payments"] == 1
    assert s["challans"]["paid"] == 3 and s["challans"]["amount_paid"] == 3000
    assert s["challans"]["overdue"] == 0
    hist = client.get("/api/challans/payments/history", headers=operator_headers).json()
    assert len(hist) == 3
    assert client.get("/api/challans/payments/history",
                      headers=auth_header("owner1@example.com")).status_code == 403


def test_overdue_loop_runs_once(monkeypatch):
    """The lifespan background task calls mark_overdue and survives errors."""
    import asyncio
    from app import main

    calls = []

    def fake():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Atlas unreachable")

    monkeypatch.setattr(main.enforcement_payments, "mark_overdue", fake)
    monkeypatch.setattr(main.enforcement_settings, "overdue_check_minutes", 0)

    async def run():
        real_sleep = asyncio.sleep

        async def fast_sleep(_):
            await real_sleep(0)
        monkeypatch.setattr(main.asyncio, "sleep", fast_sleep)
        task = asyncio.create_task(main._overdue_loop())
        while len(calls) < 2:
            await real_sleep(0.01)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2
