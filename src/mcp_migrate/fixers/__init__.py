"""Fixer registry. Drop a new module in this package and it is auto-discovered.

Exactly mirrors `rules/__init__.py`'s `all_rules()`.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from .base import Fixer, FixResult  # noqa: F401


def all_fixers() -> list[Fixer]:
    fixers: dict[str, Fixer] = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Fixer) and obj is not Fixer and getattr(obj, "rule_id", ""):
                fixers[f"{module.__name__}.{name}"] = obj()
    return sorted(fixers.values(), key=lambda f: (f.rule_id, type(f).__name__))
