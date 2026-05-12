#!/bin/bash
# Generate v1 baselines for byte-equal regression suite.
#
# This script MUST be run while checked out at v0.1-mcqc-parity tag,
# so that the v1 engine produces canonical baselines. The fixtures are
# committed to the repo and become the source of truth that Phase 2B.3's
# v2 implementation must match byte-for-byte.
#
# Usage:
#   git checkout v0.1-mcqc-parity
#   bash tests/fixtures/regression/generate_baselines.sh \
#       --netlist_dir /path/to/N2P_v1.0 \
#       --model /path/to/model.spi \
#       --waveform /path/to/wv.spi
#   git checkout feat/phase-2b1-foundation
#   git add tests/fixtures/regression/v1_baselines/
#   git commit -m "test(2b1): v1 baselines captured at v0.1-mcqc-parity"
#
# Tier-1 matrix: 5 cells x 1 corner = 5 baselines
#   Track: PNPN, VT: SVT, Corner: ffgnp_cbest_CCbest_T_125c
#   Source: docs/phase2/n2p_collateral_inventory.md section 4
#
# AIOI21 disambiguation:
#   Tier-1 anchor: AIOI21MDLIMZD0P7BWP130HPNPN3P48CPD (MZD0P7, minimum drive)
#   Ground truth:  AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD  (MZD4, used by
#                  tests/test_aioi21_ground_truth.py)
#   These are intentionally independent; do not conflate them.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUTDIR="$SCRIPT_DIR/v1_baselines"

# Parse arguments
NETLIST_DIR=""
MODEL=""
WAVEFORM=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --netlist_dir) NETLIST_DIR="$2"; shift 2 ;;
        --model)       MODEL="$2";       shift 2 ;;
        --waveform)    WAVEFORM="$2";    shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [[ -z "$NETLIST_DIR" || -z "$MODEL" || -z "$WAVEFORM" ]]; then
    echo "Usage: $0 --netlist_dir DIR --model FILE --waveform FILE"
    exit 1
fi

# Verify we are at the correct tag
CURRENT_TAG="$(git describe --exact-match --tags HEAD 2>/dev/null || echo '')"
if [[ "$CURRENT_TAG" != "v0.1-mcqc-parity" ]]; then
    echo "ERROR: Must be checked out at v0.1-mcqc-parity."
    echo "       Current: ${CURRENT_TAG:-<no tag>}"
    echo "       Run: git checkout v0.1-mcqc-parity"
    exit 1
fi

mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# Tier-1 matrix constants
# ---------------------------------------------------------------------------
CORNER="ffgnp_cbest_CCbest_T_125c"

# ---------------------------------------------------------------------------
# generate_one <cell> <arc_type> <probe_pin> <probe_dir>
#              <rel_pin> <rel_dir> <constr_pin> <constr_dir>
#              <corner> <output_stem>
#
# Pin names sourced from N2P_v1.0 netlist headers on f15eods2a.tsmc.com.
# Fail loud if a cell's netlist path is missing (never silently skip).
# ---------------------------------------------------------------------------
generate_one() {
    local cell="$1"       arc="$2"
    local probe_pin="$3"  probe_dir="$4"
    local rel_pin="$5"    rel_dir="$6"
    local constr_pin="$7" constr_dir="$8"
    local corner="$9"     stem="${10}"

    local outfile="$OUTDIR/${stem}.sp"
    echo "Generating: $stem"

    python3 "$REPO_ROOT/deckgen.py" \
        --engine legacy \
        --cell "$cell" \
        --arc_type "$arc" \
        --probe_pin "$probe_pin" \
        --probe_dir "$probe_dir" \
        --rel_pin "$rel_pin" \
        --rel_dir "$rel_dir" \
        --constr_pin "$constr_pin" \
        --constr_dir "$constr_dir" \
        --corner "$corner" \
        --netlist_dir "$NETLIST_DIR" \
        --model "$MODEL" \
        --waveform "$WAVEFORM" \
        --output "$outfile"
}

# ---------------------------------------------------------------------------
# Slot: common -- AIOI21MDLIMZD0P7BWP130HPNPN3P48CPD -- delay
# AND-OR-INVERT 2-1: inputs A1, A2 (AND) + B (OR), inverted output ZN.
# A1 rise -> ZN fall (inverting path).
# Sub-library: tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i
# ---------------------------------------------------------------------------
generate_one \
    "AIOI21MDLIMZD0P7BWP130HPNPN3P48CPD" \
    delay ZN fall A1 rise ZN fall \
    "$CORNER" \
    "AIOI21MDLIMZD0P7_delay_A1_rise_ZN_fall"

# ---------------------------------------------------------------------------
# Slot: latch -- LHCNQMZD1BWP130HPNPN3P48CPD -- hold
# Transparent latch, active-low gate GN. Hold checks data D relative to
# GN rise (closing edge of active-low gate, i.e. latch latching).
# Sub-library: tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i
# ---------------------------------------------------------------------------
generate_one \
    "LHCNQMZD1BWP130HPNPN3P48CPD" \
    hold Q rise GN rise D fall \
    "$CORNER" \
    "LHCNQMZD1_hold_GN_rise_D_fall"

# ---------------------------------------------------------------------------
# Slot: mb -- MB2SRLSDFQSXGZ1111MZD1BWP130HPNPN3P48CPD -- hold
# Multi-bank shift-register latch D-flop. CP rise = active clock edge.
# Sub-library: tcbn02p_bwph130pnpnl3p48cpd_mb_svt_c221227_400i
# ---------------------------------------------------------------------------
generate_one \
    "MB2SRLSDFQSXGZ1111MZD1BWP130HPNPN3P48CPD" \
    hold Q rise CP rise D fall \
    "$CORNER" \
    "MB2SRLSDFQSXGZ1111MZD1_hold_CP_rise_D_fall"

# ---------------------------------------------------------------------------
# Slot: sync -- SDFSYNC1QSXGMZD1BWP130HPNPN3P48CPD -- hold
# Scan-enabled synchronizer FF (replaces SLH slot; N2P ships zero SLH cells).
# Covers: scan-init, SE pin constraints, Q polarity, recovery/removal arcs.
# Sub-library: tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i
# ---------------------------------------------------------------------------
generate_one \
    "SDFSYNC1QSXGMZD1BWP130HPNPN3P48CPD" \
    hold Q rise CP rise D fall \
    "$CORNER" \
    "SDFSYNC1QSXGMZD1_hold_CP_rise_D_fall"

# ---------------------------------------------------------------------------
# Slot: mpw -- DFQSXG0MZD1BWP130HPNPN3P48CPD -- min_pulse_width
# Scan-enabled D FF. Tests minimum CP high-pulse width (CP rise -> CP fall).
# Sub-library: tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i
# ---------------------------------------------------------------------------
generate_one \
    "DFQSXG0MZD1BWP130HPNPN3P48CPD" \
    min_pulse_width Q rise CP rise CP fall \
    "$CORNER" \
    "DFQSXG0MZD1_mpw_CP_rise"

# ---------------------------------------------------------------------------
# Generate MANIFEST.json
# ---------------------------------------------------------------------------
export OUTDIR CORNER
python3 - <<'PYEOF'
import json, glob, os

outdir = os.environ["OUTDIR"]
corner = os.environ["CORNER"]
files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(outdir, "*.sp")))
manifest = {
    "version": "1",
    "corner": corner,
    "baselines": files,
}
manifest_path = os.path.join(outdir, "MANIFEST.json")
with open(manifest_path, "w") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
print(f"MANIFEST.json written: {len(files)} baselines")
PYEOF

echo ""
echo "Done. Baselines in: $OUTDIR"
echo "Next: git add tests/fixtures/regression/v1_baselines/ && git commit"
