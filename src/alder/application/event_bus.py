"""Tiny synchronous publish/subscribe event bus.

Handlers are dispatched *through* the bus synchronously from the caller's
thread; the async-ness comes from handlers themselves submitting work to the
TaskRunner (see infrastructure.async_runner). This keeps the bus simple and
deterministic while still letting the HTTP request return fast.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, DefaultDict

from alder.domain.events import DomainEvent

log = logging.getLogger(__name__)

Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: DefaultDict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        self._subs[event_type].append(handler)
        log.debug("Subscribed %s to %s", handler, event_type.__name__)

    def publish(self, event: DomainEvent) -> None:
        handlers = self._subs.get(type(event), [])
        if not handlers:
            log.debug("No subscribers for %s", type(event).__name__)
            return
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # pragma: no cover
                # One bad handler must never sabotage the rest.
                log.exception(
                    "Handler %s raised while processing %s",
                    handler,
                    type(event).__name__,
                )
