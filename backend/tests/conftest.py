"""Test setup: in-memory MongoDB (mongomock) and a temporary evidence folder.

Environment variables are set *before* the app is imported so that nothing
from the developer's real ``.env`` (e.g. the Atlas URI) is used by tests.
"""
import os
import sys
import tempfile
from pathlib import Path

import mongomock
import pymongo
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="astra-tests-")
os.environ["MONGODB_URI"] = "mongodb://test-only.invalid:27017"
os.environ["DB_NAME"] = "astra_test"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["EVIDENCE_DIR"] = os.path.join(_TMP, "evidence")
os.environ["RESULTS_DIR"] = os.path.join(_TMP, "results")
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "admin-pass"
os.makedirs(os.environ["EVIDENCE_DIR"], exist_ok=True)
os.makedirs(os.environ["RESULTS_DIR"], exist_ok=True)

pymongo.MongoClient = mongomock.MongoClient  # app.db builds its client at import time


@pytest.fixture(autouse=True)
def clean_db():
    from app import db
    from app.enforcement import challans, registry, store

    for name in db.db.list_collection_names():
        db.db.drop_collection(name)
    store.ensure_indexes()
    registry.ensure_indexes()
    challans.ensure_indexes()
    yield


@pytest.fixture
def evidence_dir():
    return os.environ["EVIDENCE_DIR"]


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)  # no context manager -> lifespan (Atlas ping / YOLO load) not run


def make_user(role: str, email: str, name: str = "Test User", **extra) -> dict:
    from app import auth, db

    doc = {"name": name, "email": email, "role": role, "password": auth.hash_pw("pw"), **extra}
    db.users.insert_one(doc)
    return doc


def auth_header(email: str) -> dict:
    from app import auth

    return {"Authorization": f"Bearer {auth.make_token(email)}"}


@pytest.fixture
def operator_headers():
    make_user("Traffic Operator", "operator@test.local", "Operator")
    return auth_header("operator@test.local")


@pytest.fixture
def admin_headers():
    make_user("Administrator", "admin@test.local", "Admin")
    return auth_header("admin@test.local")
