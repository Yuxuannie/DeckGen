"""
Static assertions for tests/fixtures/regression/generate_baselines.sh.

These tests run locally (no server, no v1 engine) and verify that the
script's Tier-1 cell/corner matrix matches the N2P collateral inventory
(docs/phase2/n2p_collateral_inventory.md section 4).

The tests parse the shell script as text; they do NOT execute it.
"""

import re
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent / "fixtures" / "regression" / "generate_baselines.sh"

# Tier-1 matrix as declared in n2p_collateral_inventory.md section 4.
TIER1_CELLS = [
    "AIOI21MDLIMZD0P7BWP130HPNPN3P48CPD",   # common (combinational delay)
    "LHCNQMZD1BWP130HPNPN3P48CPD",           # latch (hold)
    "MB2SRLSDFQSXGZ1111MZD1BWP130HPNPN3P48CPD",  # mb (hold)
    "SDFSYNC1QSXGMZD1BWP130HPNPN3P48CPD",    # sync (hold; replaces SLH)
    "DFQSXG0MZD1BWP130HPNPN3P48CPD",         # mpw (min_pulse_width)
]

TIER1_CORNER = "ffgnp_cbest_CCbest_T_125c"

# N2P cell-name regex from n2p_collateral_inventory.md section 2.
N2P_CELL_REGEX = re.compile(
    r"^([A-Z][A-Z0-9]+?)(M[A-Z0-9]+)?MZD(\d+P?\d*)"
    r"BWP130H(NPPN|PNNP|PNPN|PPNN)3P48CPD(ELVT|LVT)?$"
)


def _script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="ascii")


def test_script_exists():
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"


def test_all_tier1_cells_present():
    text = _script_text()
    for cell in TIER1_CELLS:
        assert cell in text, f"Tier-1 cell missing from script: {cell}"


def test_tier1_corner_present():
    text = _script_text()
    assert TIER1_CORNER in text, (
        f"Tier-1 corner missing from script: {TIER1_CORNER}"
    )


def test_tier1_cells_match_n2p_regex():
    for cell in TIER1_CELLS:
        assert N2P_CELL_REGEX.match(cell), (
            f"Cell does not match N2P cell-name regex: {cell}"
        )


def test_all_tier1_cells_are_pnpn_svt():
    """All Tier-1 cells must be PNPN track, SVT (no ELVT/LVT suffix)."""
    for cell in TIER1_CELLS:
        m = N2P_CELL_REGEX.match(cell)
        assert m is not None, f"Regex did not match: {cell}"
        track = m.group(4)
        vt_suffix = m.group(5)
        assert track == "PNPN", f"Expected PNPN track, got {track!r}: {cell}"
        assert vt_suffix is None, (
            f"Expected SVT (no suffix), got {vt_suffix!r}: {cell}"
        )


def test_sdfsync_replaces_slh():
    """SDFSYNC must be present (sync slot); no SLH anchor cells in matrix."""
    text = _script_text()
    assert "SDFSYNC1QSXGMZD1BWP130HPNPN3P48CPD" in text, (
        "SDFSYNC sync-slot anchor missing from script"
    )
    # The script may reference SLH in comments but must not use an SLH
    # cell name as a generate_one argument (N2P has zero SLH cells).
    # Strip comment lines before checking.
    non_comment_lines = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    non_comment_text = "\n".join(non_comment_lines)
    # No SLH cell name of the form SLH*BWP* should appear in live code.
    assert not re.search(r'SLH\w+BWP', non_comment_text), (
        "SLH cell name found in non-comment script code; "
        "N2P has zero SLH cells -- use SDFSYNC slot instead"
    )


def test_manifest_generation_present():
    """Script must contain MANIFEST.json generation logic."""
    text = _script_text()
    assert "MANIFEST.json" in text, (
        "MANIFEST.json generation missing from script"
    )


def test_tag_guard_present():
    """Script must check for v0.1-mcqc-parity tag before generating."""
    text = _script_text()
    assert "v0.1-mcqc-parity" in text, (
        "Tag guard for v0.1-mcqc-parity missing from script"
    )


def test_script_is_ascii_clean():
    """No non-ASCII bytes anywhere in the script."""
    raw = SCRIPT_PATH.read_bytes()
    bad = [i for i, b in enumerate(raw) if b > 0x7F]
    assert not bad, (
        f"Non-ASCII bytes at offsets: {bad[:5]}"
    )
