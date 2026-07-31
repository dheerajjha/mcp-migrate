"""Rule registry. Drop a new module in this package and it is auto-discovered."""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from .base import Finding, Project, Rule, SourceFile  # noqa: F401


def all_rules() -> list[Rule]:
    rules: list[Rule] = []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Rule) and obj is not Rule and obj.id:
                rules.append(obj())
    return sorted({r.id: r for r in rules}.values(), key=lambda r: r.id)
