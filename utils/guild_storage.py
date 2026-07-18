"""Per-guild JSON storage utilities."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DATA_ROOT = Path("data/guilds")


class GuildJSONStorage:
    """Async-safe JSON storage scoped to one guild and one file name."""

    def __init__(self, filename: str, default: dict[str, Any]) -> None:
        self.filename = filename
        self.default = default
        self._lock = asyncio.Lock()

    def path(self, guild_id: int) -> Path:
        """Return data/guilds/<guild_id>/<filename>."""
        return DATA_ROOT / str(guild_id) / self.filename

    async def load(self, guild_id: int) -> dict[str, Any]:
        """Load guild data, creating a default JSON file if missing."""
        async with self._lock:
            path = self.path(guild_id)
            if not path.exists():
                data = deepcopy(self.default)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                return data
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = {}
            data = deepcopy(self.default)
            data.update(current)
            return data

    async def save(self, guild_id: int, data: dict[str, Any]) -> None:
        """Persist guild data."""
        async with self._lock:
            path = self.path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
