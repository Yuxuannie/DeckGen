"""
engine/dataaccess.py -- The thin data-access boundary (spec SS7.3).

One interface (DataAccess), two backends:
  - FixtureBackend : local, synthetic, PDK-free; lives in the repo.
  - RealBackend    : points at server collateral (SEGMENT 2 / air-gapped run).

Swapping them is a CONFIG change ("backend": "fixture" | "real"), never an
engine-code change. Engine stages import nothing from here except the abstract
DataAccess type; they ask it for netlist / arc / measurement / model and stay
ignorant of where those bytes came from.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict


class DataAccess(ABC):
    """Uniform read-only access to the four artifacts a stage may need."""

    name: str = "abstract"

    @abstractmethod
    def read_netlist(self, cell: str) -> str:
        """Return the .subckt netlist text for a cell."""

    @abstractmethod
    def read_arc(self, arc_id: str) -> Dict[str, Any]:
        """Return the define_arc-style record (spec SS3 arc fields) as a dict."""

    @abstractmethod
    def read_measurement_block(self, arc: Dict[str, Any]) -> str:
        """Return Liberate's opaque measurement block, passed through UNCHANGED."""

    @abstractmethod
    def read_model(self) -> str:
        """Return the generic (PDK-free) device model text."""


class _FileBackend(DataAccess):
    """Shared file layout for both fixture and real backends.

    Layout under <root>:
      <cell>.subckt
      arcs/<arc_id>.json
      measurement_block_placeholder.sp
      generic_mos.model
    """

    def __init__(self, root: str, name: str):
        self.root = root
        self.name = name
        if not os.path.isdir(root):
            raise FileNotFoundError(
                f"[{name}] data root not found: {root}\n"
                f"  fixture backend: check engine/fixtures exists.\n"
                f"  real backend: point 'real_root' at server collateral (SEGMENT 2)."
            )

    def _read(self, *parts: str) -> str:
        path = os.path.join(self.root, *parts)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"[{self.name}] missing artifact: {path}")
        with open(path, "r", encoding="ascii") as fh:
            return fh.read()

    def read_netlist(self, cell: str) -> str:
        # Accept common netlist extensions so the real .spi need not be renamed.
        for ext in (".subckt", ".spi", ".sp", ".cdl"):
            path = os.path.join(self.root, f"{cell}{ext}")
            if os.path.isfile(path):
                with open(path, "r", encoding="ascii") as fh:
                    return fh.read()
        raise FileNotFoundError(
            f"[{self.name}] no netlist for cell {cell!r} in {self.root} "
            f"(tried .subckt/.spi/.sp/.cdl)"
        )

    def read_arc(self, arc_id: str) -> Dict[str, Any]:
        return json.loads(self._read("arcs", f"{arc_id}.json"))

    def read_measurement_block(self, arc: Dict[str, Any]) -> str:
        return self._read("measurement_block_placeholder.sp")

    def read_model(self) -> str:
        return self._read("generic_mos.model")


class FixtureBackend(_FileBackend):
    """Local synthetic data (spec SS8). PDK-free, lives in the repo."""

    def __init__(self, root: str):
        super().__init__(root, "fixture")


class RealBackend(_FileBackend):
    """Server collateral. Identical code path; only the root differs (spec SS7.2)."""

    def __init__(self, root: str):
        super().__init__(root, "real")


def make_data_access(config: Dict[str, Any], base_dir: str) -> DataAccess:
    """Select the backend from config -- the single switch point (spec SS7.3)."""
    backend = config.get("backend")
    if backend == "fixture":
        root = os.path.join(base_dir, config.get("fixture_root", "fixtures"))
        return FixtureBackend(root)
    if backend == "real":
        return RealBackend(config["real_root"])
    raise ValueError(
        f"config 'backend' must be 'fixture' or 'real', got {backend!r}"
    )
