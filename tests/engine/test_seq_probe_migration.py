import os
from tools.seq_probe import analyze

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_probe_sdfx_reports_ff_chain():
    # After migration the probe delegates to classify(); SDFX is a depth-1
    # master/slave FF-chain.
    report, guess, bucket = analyze(_SDFX, "SDFX_LPE_PLACEHOLDER", anon=True)
    assert "ff_chain" in (guess + " " + bucket + " " + report).lower()
