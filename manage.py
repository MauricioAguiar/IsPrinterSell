#!/usr/bin/env python
"""Django management entry point."""
import os
import sys
from pathlib import Path


def main() -> None:
    # Put ./src on sys.path so `alder` is importable without an editable install.
    src = Path(__file__).resolve().parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "alder.interfaces.django_app.settings"
    )
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is not installed. Run `pip install -e .[dev]` first."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
