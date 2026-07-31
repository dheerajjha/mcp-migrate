"""The old resource-not-found error code, kept in its own module so the
fixer round-trip test can exercise the R017 fixer alongside the others."""
from __future__ import annotations


def read_resource(handle: str) -> dict:
    if not _exists(handle):
        return {"code": -32002, "message": "resource not found"}
    return {"contents": _load(handle)}


def _exists(handle: str) -> bool:
    raise NotImplementedError


def _load(handle: str) -> str:
    raise NotImplementedError
