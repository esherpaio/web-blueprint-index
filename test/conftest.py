import sys
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def stop_cache_manager() -> Iterator[None]:
    """Stop the manager started by older web-framework releases on import."""
    yield
    manager_module = sys.modules.get("web.cache.manager")
    if manager_module is None:
        return

    manager = manager_module.cache_manager
    stop = getattr(manager, "stop", None)
    if stop is None:
        stop = manager._on_shutdown
    stop()
