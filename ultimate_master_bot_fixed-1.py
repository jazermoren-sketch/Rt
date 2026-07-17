"""Compatibility entrypoint.

Run `python bot.py` for the modular project. This wrapper remains so older
process managers that still point at the original file continue to work.
"""
from __future__ import annotations

import asyncio

from bot import main


if __name__ == "__main__":
    asyncio.run(main())
