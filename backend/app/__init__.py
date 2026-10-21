"""CANalyst backend package."""
from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.1.0"


def _load_env(path: Path = Path(__file__).resolve().parents[1] / ".env") -> None:
    """Read KEY=value lines from backend/.env without overriding the shell.

    Keeps API keys out of the repository and out of shell history; see
    .env.example for the variables.
    """
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env()
