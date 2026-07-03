"""
engine/golden_env.py -- golden-deck collateral + timing, parsed from the
SDFQSXG hold(CP,D) golden deck screenshots (verified valid by Yuxuan 2026-06-04).

Single source of truth for the P2 simulation deck. The engine REUSES these
.inc paths and timing params so the P2 run matches the golden environment; it
only adds internal-node probes + a settle-point measurement. If a server path
moves, edit it HERE only.

Source: golden deck `hold/template__common__rise__fall__1.sp` for
ssgnp_0p450v_m40c, cell SDFQSXG0MZD1BWP130HPNPN3P48CPD.
"""
from __future__ import annotations

# --- .inc collateral (golden deck lines 20/23/26) ---
INC_WAVEFORM = "/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/std_wv_c651.spi"
INC_MODEL = ("/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/"
             "0-FMC_golden/gen_DECKs/ssgnp_0p450v_m40c_DECKS/hold/"
             "ssgnp_0p450v_m40c_cworst_CCworst_T.hold.inc")
INC_NETLIST = ("/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/"
               "0-FMC_golden/Collaterals/kits/base/3svt/Netlist/"
               "LPE_cworst_CCworst_T_m40c/SDFQSXG0MZD1BWP130HPNPN3P48CPD.spi")

# --- corner (golden deck lines 29-31) ---
VDD_VALUE = "0.450"
VSS_VALUE = "0"
TEMP = "-40"

# --- load + slews (golden deck lines 34-36) ---
CL = "0.000542p"
REL_PIN_SLEW = "0.4988n"      # CP slew
CONSTR_PIN_SLEW = "0.5336n"   # D slew

# --- waveform timestamps (golden deck lines 52-59), as multiples of max_slew ---
MAX_SLEW = "7.9962n"
# related (clock CP) edges and constrained (D) edges
RELATED_T = {"t01": "0.0n", "t02": "10 * max_slew", "t03": "20 * max_slew",
             "t04": "30 * max_slew", "t05": "40 * max_slew"}
CONSTR_T = {"t01": "5 * max_slew", "t02": "20 * max_slew"}

# --- transient (golden deck line 87) ---
TRAN = ".tran 1p 5000n sweep monte=1 monte=1"

# Subckt port order, from the netlist .subckt line.
PORTS = ["SI", "D", "SE", "CP", "Q", "VDD", "VSS", "VPP", "VBB"]
