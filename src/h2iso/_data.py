"""Internal helper for locating bundled data files via importlib.resources.

This indirection lets the package work both in editable (`pip install -e .`)
and wheel/zipimport installations without relying on `__file__` path math.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator


@contextmanager
def data_path(category: str, filename: str) -> Iterator[Path]:
    """Yield a concrete filesystem :class:`Path` for a bundled data file.

    Parameters
    ----------
    category:
        Sub-directory under ``h2iso/data``, e.g. ``"parameters"`` or ``"schemas"``.
    filename:
        File name within the category directory, e.g. ``"species.json"``.

    Yields
    ------
    pathlib.Path
        A real filesystem path. When the package lives inside a zip/wheel,
        ``importlib.resources.as_file`` extracts a temporary copy whose lifetime
        is bound to this context manager.
    """
    resource = resources.files("h2iso").joinpath("data", category, filename)
    with resources.as_file(resource) as concrete_path:
        yield concrete_path
