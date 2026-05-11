"""
backends/hspice.py -- HSPICE backend stub.

Implements BackendInterface for HSPICE (.sp files).  All methods raise
NotImplementedError in Phase 2A.  Full implementation is Phase 2C scope.

HSPICE is the default backend for all non-delay arcs and for HSPICE delay
arcs (OPTIMIZE .tran style).

Source: spec_draft.md SS2 (backends/ section), E2_sampling_results.md SS A.
"""

from core.principle_engine.backends import BackendInterface
from core.principle_engine.family_types import TranStyle


class HspiceBackend(BackendInterface):
    """HSPICE-specific deck assembly.

    Phase 2A stub: all methods raise NotImplementedError.
    Phase 2C will provide full implementations based on analysis of v1
    deck_builder.py and sampled template structure.

    HSPICE .tran styles (from E2_sampling_results.md SS A):
      MONTE_CARLO:  .tran 1p 5000n sweep monte=1
      OPTIMIZE:     .tran 1p 5000n sweep OPTIMIZE=OPT1 results=...
      BARE:         .tran 1p 400ns
    """

    def emit_simulator_directive(self) -> str:
        """HSPICE is native; no simulator switching directive needed.

        Phase 2A stub.
        """
        raise NotImplementedError(
            "HspiceBackend.emit_simulator_directive: Phase 2C implementation pending"
        )

    def emit_options(self, **kwargs) -> str:
        """Return HSPICE .options block.

        Expected output example:
            .options INGOLD=2 ACCURATE=1 PROBE=1 POST=1

        Phase 2A stub.
        """
        raise NotImplementedError(
            "HspiceBackend.emit_options: Phase 2C implementation pending"
        )

    def emit_tran(self, tran_style, tran_stop: str = "5000n",
                  opt_name: str = "OPT1") -> str:
        """Return HSPICE .tran command.

        Expected output by tran_style:
          MONTE_CARLO:  .tran 1p 5000n sweep monte=1
          OPTIMIZE:     .tran 1p 5000n sweep OPTIMIZE=OPT1 results=cp2q_del1
          BARE:         .tran 1p 400ns

        Phase 2A stub.
        """
        raise NotImplementedError(
            "HspiceBackend.emit_tran: Phase 2C implementation pending"
        )

    def emit_measure(self, meas_name: str, signal: str,
                     edge_dir: str, **kwargs) -> str:
        """Return HSPICE .meas tran statement.

        Expected output example:
            .meas tran cp2q_del1 trig v(CP) val='vdd_value/2' rise=1
                                 targ v(Q) val='vdd_value/2' rise=1

        Phase 2A stub.
        """
        raise NotImplementedError(
            "HspiceBackend.emit_measure: Phase 2C implementation pending"
        )
