"""Lazy accessor for the optional CasADi dependency.

CasADi is an optional extra (``h2iso[solver]``).  Importing :mod:`h2iso` (or
any of the mesh / flowsheet modules) must succeed when CasADi is not
installed, so this module exposes :data:`ca` as a proxy that imports
``casadi`` only on the first attribute access.  Failing late gives an
actionable error instead of a bare ``ModuleNotFoundError`` at import time.
"""

from __future__ import annotations

import importlib
from types import ModuleType

_INSTALL_HINT = (
    "h2iso.mesh requires the optional 'casadi' dependency; "
    "install it with: pip install 'h2iso[solver]'"
)


class _LazyCasadi:
    """Proxy that imports :mod:`casadi` on first attribute access."""

    __slots__ = ("_module",)

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    def _load(self) -> ModuleType:
        module = self._module
        if module is None:
            try:
                module = importlib.import_module("casadi")
            except ImportError as exc:
                raise ImportError(_INSTALL_HINT) from exc
            self._module = module
        return module

    def __getattr__(self, name: str):
        return getattr(self._load(), name)

    def __repr__(self) -> str:
        return f"<lazy casadi proxy loaded={self._module is not None}>"


ca = _LazyCasadi()
