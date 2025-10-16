from __future__ import annotations

import pytest

from app.services.migration import set_migration_service


@pytest.fixture(autouse=True)
def reset_migration_service() -> None:
    set_migration_service(None)
    yield
    set_migration_service(None)
