"""Cross-module event subscription wiring.

Modules avoid importing each other (Blueprint §8.2 rule 1). Each module
exposes a `register(bus)` function in its `event_handlers.py`, and this
file is the single place that imports them all and wires them to the
shared event bus at app startup. Adding a new module-level subscription:
add one line here.

Tests that exercise events (cf. `tests/integration/test_event_bus.py`)
call `reset_bus_for_tests()` then re-invoke `register_all` if they need
the production wiring.
"""
from __future__ import annotations

import logging

from app.infrastructure.event_bus import InProcessEventBus

logger = logging.getLogger("nexhire.wiring")


def register_all(bus: InProcessEventBus) -> None:
    from app.modules.lifecycle import event_handlers as lifecycle_handlers
    from app.modules.nda import event_handlers as nda_handlers
    from app.modules.notification import event_handlers as notification_handlers
    from app.modules.onboarding import event_handlers as onboarding_handlers
    from app.modules.workflow import event_handlers as workflow_handlers

    notification_handlers.register(bus)
    workflow_handlers.register(bus)
    onboarding_handlers.register(bus)
    nda_handlers.register(bus)
    lifecycle_handlers.register(bus)
    logger.info("nexhire.wiring.event_handlers_registered")
