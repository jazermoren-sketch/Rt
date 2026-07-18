"""Franco/Arabizi text transformation utilities."""
from __future__ import annotations

DEFAULT_FRANCO_MAP: dict[str, str] = {
    "ع": "3", "ح": "7", "خ": "5", "ق": "9", "ء": "2", "ؤ": "2", "ئ": "2",
    "أ": "2", "إ": "2", "آ": "2", "ص": "9", "ط": "6", "ض": "d",
}


def to_franco(text: str | None, mapping: dict[str, str] | None = None) -> str:
    """Convert supported Arabic letters to Franco without touching links/files/numbers-only text."""
    if not text:
        return ""
    mapping = mapping or DEFAULT_FRANCO_MAP
    if not any(char in text for char in mapping):
        return text
    parts: list[str] = []
    for token in text.split(" "):
        if token.startswith(("http://", "https://", "www.")):
            parts.append(token)
        else:
            for arabic, franco in mapping.items():
                token = token.replace(arabic, franco)
            parts.append(token)
    return " ".join(parts)
