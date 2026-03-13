import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command

TEST_DB_PATH = Path("/tmp") / f"gametracker-test-{uuid4().hex}.sqlite3"

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["SUPERADMIN_USERNAME"] = "test_admin"
os.environ["SUPERADMIN_PASSWORD"] = "test_password_123"
os.environ["SECRET_KEY"] = "test-secret-key-change-me"

from app.main import app  # noqa: E402


def run_test_migrations() -> None:
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def client():
    run_test_migrations()
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
