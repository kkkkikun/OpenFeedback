"""Shared test fixtures.

Each test gets its own SQLite file and its own data directory, so tests
never see each other's rows and a failed run leaves no state behind.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# The app reads its configuration at import time, so the environment must be
# set before `app.config` is imported anywhere.
_TMP = Path(tempfile.mkdtemp(prefix="of-test-"))
os.environ["OF_DATA_DIR"] = str(_TMP / "data")
os.environ["OF_DATABASE_URL"] = f"sqlite:///{_TMP / 'data' / 'test.db'}"
os.environ["OF_ATTACHMENTS_DIR"] = str(_TMP / "data" / "attachments")
os.environ["OF_ADMIN_USERNAME"] = "tester"
os.environ["OF_ADMIN_PASSWORD"] = "test-password-123"
os.environ["OF_COOKIE_SECURE"] = "false"
os.environ["OF_ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import App  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    settings = get_settings()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.attachments_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit counters are process-wide, so clear them between tests.

    Without this the tenth test in a run would be rejected by the limit that
    the first nine consumed.
    """
    from app.ratelimit import login_limiter, submission_limiter

    submission_limiter.reset()
    login_limiter.reset()
    yield
    submission_limiter.reset()
    login_limiter.reset()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def app_row(client: TestClient) -> App:
    """A registered, enabled app used by most tests."""
    from sqlalchemy import select

    from app.db import session_scope

    with session_scope() as session:
        row = session.scalar(select(App).where(App.app_id == "localpixt"))
        if row is None:
            row = App(app_id="localpixt", name="显影", platform="android")
            session.add(row)
            session.flush()
            row_id = row.id
        else:
            row_id = row.id
    return App(id=row_id, app_id="localpixt", name="显影", platform="android")


@pytest.fixture
def admin_login(client: TestClient) -> str:
    """Log in as the bootstrap admin and return the CSRF token."""
    response = client.post(
        "/api/v1/admin/login",
        json={"username": "tester", "password": "test-password-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrfToken"]
