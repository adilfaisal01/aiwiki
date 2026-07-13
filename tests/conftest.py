import os
import tempfile
import uuid
from pathlib import Path

_test_db = Path(tempfile.gettempdir()) / "aiwiki_pytest.db"
if _test_db.exists():
    _test_db.unlink()
os.environ["AIWIKI_DATABASE_URL"] = f"sqlite:///{_test_db}"
os.environ["AIWIKI_DISABLE_AGENT_LOOP"] = "true"
os.environ["AIWIKI_EXTERNAL_RATE_LIMIT"] = "100"
os.environ["AIWIKI_REGISTRATION_RATE_LIMIT"] = "100"
os.environ["AIWIKI_WIKI_EDIT_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def signed_in_client(client):
    response = client.post(
        "/api/v1/account",
        json={
            "email": f"user-{uuid.uuid4().hex[:10]}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    return client
