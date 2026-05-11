"""
core/principle_engine/backends -- Backend-specific deck assembly.

Each backend implements the BackendInterface. The engine calls these hooks
and never emits backend-specific syntax directly.

Backends:
  hspice.py   -- HSPICE (.sp files); default for all non-delay arcs
  spectre.py  -- Spectre (.thanos.sp files); dominant for delay arcs (94 files)

Source: spec_draft.md SS2 (backends/ section), E2_sampling_results.md SS D.
"""

from abc import ABC, abstractmethod


class BackendInterface(ABC):
    """Uniform interface that both HSPICE and Spectre backends implement.

    Phase 2A: methods raise NotImplementedError (stubs).
    Phase 2C: full implementations.
    """

    @abstractmethod
    def emit_simulator_directive(self) -> str:
        """Return simulator-switching directive line(s).

        HSPICE: empty string (HSPICE is native).
        Spectre: "simulator lang=spectre\\n"
        """

    @abstractmethod
    def emit_options(self, **kwargs) -> str:
        """Return simulator options block.

        HSPICE: ".options INGOLD=2 ACCURATE=1 ..."
        Spectre: "simulatorOptions options ..."
        """

    @abstractmethod
    def emit_tran(self, tran_style, tran_stop: str = "5000n",
                  opt_name: str = "OPT1") -> str:
        """Return transient simulation command.

        Args:
            tran_style: TranStyle enum value.
            tran_stop:  Stop time string (e.g., "5000n", "400ns").
            opt_name:   OPTIMIZE parameter name (HSPICE OPTIMIZE style only).
        """

    @abstractmethod
    def emit_measure(self, meas_name: str, signal: str,
                     edge_dir: str, **kwargs) -> str:
        """Return a single measurement statement.

        Args:
            meas_name: Measurement result variable name.
            signal:    Node to measure.
            edge_dir:  "rise" or "fall".
        """


__all__ = ["BackendInterface"]
