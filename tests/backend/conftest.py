import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_environment():
    temp_dir = tempfile.TemporaryDirectory(prefix="roomtask_tests_")
    root = Path(temp_dir.name)

    os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
    os.environ["UPLOAD_DIR"] = str(root / "uploads")
    os.environ["JWT_SECRET"] = "roomtask-isolated-test-secret-not-for-production"
    os.environ["ADMIN_USERNAME"] = "testadmin"
    os.environ["ADMIN_PASSWORD"] = "TestAdminPassword123!"
    os.environ["DISCORD_BOARD_API_KEY"] = ""
    os.environ["DISCORD_WEBHOOK_URL"] = ""

    (root / "uploads").mkdir(parents=True, exist_ok=True)

    yield root

    temp_dir.cleanup()


@pytest.fixture(scope="session")
def app(test_environment):
    from app.main import app

    return app


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client