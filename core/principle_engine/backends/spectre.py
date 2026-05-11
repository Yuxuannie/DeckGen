"""
backends/spectre.py -- Spectre backend stub.

Implements BackendInterface for Spectre (.thanos.sp files).  All methods
raise NotImplementedError in Phase 2A.  Full implementation is Phase 2C scope.

Spectre is used for delay arcs in the N2P_v1.0 corpus:
  - 94 .thanos.sp files total
  - 91 in delay/ (97%), 3 in hold/
  - Standalone complete templates, not patches on HSPICE templates
  - Use "simulator lang=spectre" switching directive
  - .tran equivalent: "tranIter tran stop=5000n"

Source: spec_draft.md SS2 (backends/ section), E2_sampling_results.md SS D.
"""

from core.principle_engine.backends import BackendInterface
from core.principle_engine.family_types import TranStyle


class SpectreBackend(BackendInterface):
    """Spectre-specific deck assembly.

    Phase 2A stub: all methods raise NotImplementedError.
    Phase 2C will provide full implementations based on Task E.3 sampling
    of 3 additional non-AO22 Spectre files (currently in progress).

    Spectre syntax differences from HSPICE:
      - Requires "simulator lang=spectre" directive at top
      - Transient: "tranIter tran stop=5000n ..." instead of ".tran"
      - Measurements: "meas_name (signal) measure ..." instead of ".meas tran"
      - Options: "simulatorOptions options ..." instead of ".options"
    """

    def emit_simulator_directive(self) -> str:
        """Return Spectre simulator switching directive.

        Expected output:
            simulator lang=spectre

        Phase 2A stub.
        """
        raise NotImplementedError(
            "SpectreBackend.emit_simulator_directive: Phase 2C implementation pending. "
            "Task E.3 (sample 3 non-AO22 Spectre files) must complete first."
        )

    def emit_options(self, **kwargs) -> str:
        """Return Spectre simulatorOptions block.

        Expected output example:
            simulatorOptions options scale=1e-6 accurate=yes

        Phase 2A stub.
        """
        raise NotImplementedError(
            "SpectreBackend.emit_options: Phase 2C implementation pending"
        )

    def emit_tran(self, tran_style, tran_stop: str = "5000n",
                  opt_name: str = "OPT1") -> str:
        """Return Spectre transient simulation command.

        Expected output:
            tranIter tran stop=5000n errpreset=moderate

        tran_style must be TranStyle.SPECTRE_TRAN_ITER for this backend.

        Phase 2A stub.
        """
        raise NotImplementedError(
            "SpectreBackend.emit_tran: Phase 2C implementation pending"
        )

    def emit_measure(self, meas_name: str, signal: str,
                     edge_dir: str, **kwargs) -> str:
        """Return Spectre measurement statement.

        Expected output example (Spectre syntax):
            cp2q_del1 (CP Q) delay rise=1 fall=1

        Phase 2A stub.
        """
        raise NotImplementedError(
            "SpectreBackend.emit_measure: Phase 2C implementation pending. "
            "Spectre measurement syntax differs from HSPICE .meas tran."
        )
