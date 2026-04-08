"""Django-side accessor for the DI container.

Keeping this thin module between Django and :mod:`alder.bootstrap` lets the
views import ``from .container import container`` without dragging the
infrastructure layer into the URL conf.
"""
from __future__ import annotations

from alder.bootstrap import get_container


def container():
    return get_container()
