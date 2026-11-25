from pathlib import Path

import pytest

from kai.storage.database import Database
from kai.storage.repository import Repository


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    return Repository(Database(tmp_path / "test.db"))
