"""Lightweight thread-pool task runner.

Why not Celery?
    For a single-user desktop ERP, Celery + Redis is enormous overkill. A
    persistent thread-pool behind a simple ``submit()`` API keeps Django
    responses fast without adding infrastructure. Tasks that fail are logged
    — they do NOT crash the worker or raise into the HTTP thread.
"""
from __future__ import annotations

import atexit
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)


class ThreadPoolTaskRunner:
    def __init__(self, max_workers: int | None = None) -> None:
        workers = max_workers or int(os.getenv("ALDER_ASYNC_WORKERS", "2"))
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="alder-async"
        )
        self._closed = False
        atexit.register(self.shutdown)

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> None:
        if self._closed:  # pragma: no cover
            log.warning("TaskRunner is closed; dropping task %s", fn)
            return
        fut: Future = self._executor.submit(fn, *args, **kwargs)
        fut.add_done_callback(self._log_failure)

    @staticmethod
    def _log_failure(fut: Future) -> None:
        exc = fut.exception()
        if exc is not None:
            log.exception("Async task failed", exc_info=exc)

    def shutdown(self, *, wait: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=not wait)
