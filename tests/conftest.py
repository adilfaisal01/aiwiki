import os
import tempfile
from pathlib import Path

_test_db = Path(tempfile.gettempdir()) / "aiwiki_pytest.db"
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
