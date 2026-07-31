"""Durable, handle-addressed note storage.

No connection state lives here: `handle` is an opaque key issued by the
caller (backed by a database in a real deployment) so any process can serve
any request -- there is nothing tying a handle to the server instance that
created it.
"""
from __future__ import annotations

import json
from pathlib import Path


class NoteStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("/var/lib/notes-server")

    def _path(self, handle: str) -> Path:
        return self.root / f"{handle}.json"

    def read(self, handle: str) -> list[str]:
        path = self._path(handle)
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def append(self, handle: str, text: str) -> None:
        notes = self.read(handle)
        notes.append(text)
        self._path(handle).write_text(json.dumps(notes))

    def clear(self, handle: str) -> None:
        path = self._path(handle)
        if path.exists():
            path.unlink()
