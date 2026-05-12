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
#       --netlist_dir /path/to/netlists \
#       --model /path/to/model.spi \
#       --waveform /path/to/wv.spi
#   git checkout feat/phase-2b1-foundation
#   git add tests/fixtures/regression/v1_baselines/
#   git commit -m "test(2b1): v1 baselines captured at v0.1-mcqc-parity"
#
# Cell/corner matrix:
#   Cells and corners below must be confirmed by Yuxuan before running.
#   See Phase 2B.1 Step 4a output for the proposal and confirmation record.
#
# Current status: PLACEHOLDER -- cell names and corners not yet confirmed.
#   DO NOT RUN until Yuxuan confirms the cell list and corner set.

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
# Cell x arc x corner matrix
# TODO: Yuxuan to confirm exact cell names from production cell library
#       before running this script. Replace PLACEHOLDER entries below.
#
# Format: generate_one <cell> <arc_type> <rel_pin> <rel_dir> <constr_pin>
#         <constr_dir> <corner> <output_stem>
#
# Proposed cells (Phase 2B.1 Step 4a):
#   Family 1 (COMMON):  DFFQ1BWP<suffix>       hold, setup, min_pulse_width
#   Family 2 (LATCH):   LHQD1BWP<suffix>       hold
#   Family 3 (MB):      MB<variant>SRLSDF<suf>  hold
#   Family 4 (SLH):     SLH<variant>BWP<suffix> hold
#   Family 5 (common mpw): same DFFQ1BWP cell, min_pulse_width arc
#
# Proposed corners (awaiting Yuxuan confirmation):
#   ssgnp_0p450v_m40c  (SS corner)
#   ttgnp_0p800v_25c   (TT corner)
#   ffgnp_0p900v_125c  (FF corner)
# ---------------------------------------------------------------------------

generate_one() {
    local cell="$1" arc="$2" rel_pin="$3" rel_dir="$4"
    local constr_pin="$5" constr_dir="$6" corner="$7" stem="$8"

    local outfile="$OUTDIR/${stem}.sp"
    echo "Generating: $stem"

    python3 "$REPO_ROOT/deckgen.py" \
        --engine legacy \
        --cell "$cell" \
        --arc_type "$arc" \
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
# PLACEHOLDER matrix -- replace with confirmed cell names + corners
# ---------------------------------------------------------------------------
echo "Cell/corner matrix: PLACEHOLDER. Yuxuan must confirm before running."
echo "Edit this script (generate_baselines.sh) to fill in the matrix."
echo ""
echo "Proposed matrix size: ~5 cells x 3 arc types x 3 corners = ~45 baselines"
echo "Output directory: $OUTDIR"
echo ""
echo "To populate: replace the placeholder calls below with actual generate_one calls."
echo "Example (uncomment and edit):"
echo ""
echo "  # Family 1 hold -- SS corner"
echo "  # generate_one DFFQ1BWP130H hold CP rise D fall ssgnp_0p450v_m40c DFFQ1BWP130H_hold_rise_fall_ssg"
echo ""
echo "STOPPED. Not generating any baselines until matrix is confirmed."
exit 0
