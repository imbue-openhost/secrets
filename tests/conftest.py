from collections.abc import Iterator
from pathlib import Path

import pytest
from openhost_test_harness import OpenhostStack

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def stack() -> Iterator[OpenhostStack]:
    with OpenhostStack(app_dir=REPO_ROOT) as s:
        yield s
