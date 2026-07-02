from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

_main = import_module(".main", __name__)


class _AppModule(ModuleType):
    def __getattr__(self, name: str):
        return getattr(_main, name)

    def __setattr__(self, name: str, value) -> None:
        setattr(_main, name, value)
        super().__setattr__(name, value)


module = sys.modules[__name__]
module.__class__ = _AppModule  # type: ignore[misc]

for _attr in dir(_main):
    if not _attr.startswith("__"):
        setattr(module, _attr, getattr(_main, _attr))
