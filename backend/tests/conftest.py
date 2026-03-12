import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path(__file__).resolve().parent / ".test-db.sqlite3"

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["SUPERADMIN_USERNAME"] = "test_admin"
os.environ["SUPERADMIN_PASSWORD"] = "test_password_123"
os.environ["SECRET_KEY"] = "test-secret-key-change-me"

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture()
def auth_headers(client: TestClient):
    response = client.post(
        "/api/auth/login",
        data={"username": "test_admin", "password": "test_password_123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
