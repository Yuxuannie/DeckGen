"""
engine/config.py -- Config load + path anchoring.

Config is plain JSON (stdlib only, so the skeleton runs on an air-gapped box
with no pip installs). The only meaningful key for SEGMENT 1 is 'backend',
which picks the data-access implementation (spec SS7.3).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

# Anchor every relative path to this package dir, never to the cwd
# (project convention in CLAUDE.md: paths relative to script location).
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(ENGINE_DIR, "config.fixture.json")


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="ascii") as fh:
        return json.load(fh)
