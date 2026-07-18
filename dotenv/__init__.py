"""Minimal local dotenv loader used when python-dotenv is unavailable."""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(dotenv_path: str | os.PathLike[str] = ".env", *, override: bool = False, encoding: str = "utf-8") -> bool:
    """Load key=value pairs from a .env file into os.environ.

    This implements the subset needed by the bot while remaining compatible with
    the `from dotenv import load_dotenv` import style used by python-dotenv.
    """
    path = Path(dotenv_path)
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding=encoding).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
    return True
