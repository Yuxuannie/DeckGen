"""Delay template mapping rules extracted from MCQC hack_template_v2/funcs.py.

This is a faithful reproduction of the if-chain from the MCQC source.
Each rule checks: arc_type in delay_arc_types, cell_name (fnmatch),
constr_pin, constr_pin_dir, rel_pin, rel_pin_dir, and optionally when.

Rules are evaluated in order. First match wins.
"""

import fnmatch

delay_arc_types = [
    "combinational",
    "combinational_fall", "combinational_rise",
    "edge", "falling_edge", "rising_edge",
    "three_state_disable", "three_state_enable",
    "clear", "preset",
]


def get_delay_template(cell_name, arc_type, constr_pin, constr_pin_dir,
                       rel_pin, rel_pin_dir, when=None):
    """Match delay template using MCQC hack_template_v2 rules.

    Args:
        cell_name: full cell name
        arc_type: e.g. 'combinational', 'edge', etc.
        constr_pin: constrained/output pin (e.g. 'ZN', 'Q', 'Z')
        constr_pin_dir: 'rise' or 'fall'
        rel_pin: related/input pin (e.g. 'A1', 'CP', 'I')
        rel_pin_dir: 'rise' or 'fall'
        when: when condition string or None

    Returns:
        template relative path (str) or None
    """
    if arc_type not in delay_arc_types:
        return None

    when = when or ''

    # -------- XOR3D --------
    if (fnmatch.fnmatch(cell_name, "XOR3D*") and
            constr_pin == "Z" and constr_pin_dir == "fall" and
            rel_pin == "A2" and rel_pin_dir == "fall" and
            "!A1&!A3" in when):
        return "delay/hack/template__xor3dX__fall.sp"

    # -------- XNR4D --------
    if (fnmatch.fnmatch(cell_name, "XNR4D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "A3" and rel_pin_dir == "rise" and
            "!A1&!A2&!A4" in when):
        return "delay/hack/template__XNR4D__fall.sp"

    # -------- OAI33D --------
    if (fnmatch.fnmatch(cell_name, "OAI33D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "B3" and rel_pin_dir == "rise" and
            "A1&!A2&A3&!B1&!B2" in when):
        return "delay/hack/template__OAI33D_inpin_rise_delay_fall.sp"

    # -------- SDFNQSXGD --------
    if (fnmatch.fnmatch(cell_name, "SDFNQSXGD*") and
            constr_pin == "Q" and constr_pin_dir == "rise" and
            rel_pin == "CPN" and rel_pin_dir == "fall" and
            "!SE&SI" in when):
        return "delay/hack/template__SDFNQSXGD_inpin_fall_delay_rise.sp"

    # -------- FCICOD --------
    if (fnmatch.fnmatch(cell_name, "FCICOD*") and
            constr_pin == "CO" and constr_pin_dir == "fall" and
            rel_pin == "CI" and rel_pin_dir == "fall" and
            "!A&B" in when):
        return "delay/template__FCICOD_inpin_fall_delay_fall.sp_anh"

    # -------- INVD --------
    if (fnmatch.fnmatch(cell_name, "INVD*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "I" and rel_pin_dir == "rise"):
        return "delay/template__invdX__fall.sp"

    # -------- BUFTD (wildcard cell match) --------
    if (fnmatch.fnmatch(cell_name, "*") and
            constr_pin == "Z" and constr_pin_dir == "fall" and
            rel_pin == "I" and rel_pin_dir == "fall"):
        return "delay/./template__BUFTD_inpin_fall_delay_fall.sp"

    # -------- SDFQSXGD --------
    if (fnmatch.fnmatch(cell_name, "SDFQSXGD*") and
            constr_pin == "Q" and constr_pin_dir == "fall" and
            rel_pin == "CP" and rel_pin_dir == "rise" and
            "!D&!SE&!SI" in when):
        return "delay/hack/template__SDFQSXGD_inpin_rise_delay_fall.sp"

    # -------- CKLHQD --------
    if (fnmatch.fnmatch(cell_name, "CKLHQD*") and
            constr_pin == "Q" and constr_pin_dir == "fall" and
            rel_pin == "CPN" and rel_pin_dir == "fall" and
            "E&TE" in when):
        return "delay/hack/template__CKLHQD_inpin_rise_delay_fall.sp"

    # -------- AOI33D (A1 input) --------
    if (fnmatch.fnmatch(cell_name, "AOI33D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "A1" and rel_pin_dir == "rise" and
            "A2&A3&!B1&B2&B3" in when):
        return "delay/hack/template__AOI33D_inpin_rise_delay_fall.sp"

    # -------- CKLNQD --------
    if (fnmatch.fnmatch(cell_name, "CKLNQD*") and
            constr_pin == "Q" and constr_pin_dir == "fall" and
            rel_pin == "CP" and rel_pin_dir == "fall" and
            "!E&!TE" in when):
        return "delay/hack/template__CKLNQD_inpin_fall_delay_fall.sp"

    # -------- AOI222D --------
    if (fnmatch.fnmatch(cell_name, "AOI222D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "A1" and rel_pin_dir == "rise" and
            "A2&B1&!B2&C1&!C2" in when):
        return "delay/hack/template__AOI2220PTPBD_inpin_rise_delay_fall.sp"

    # -------- SDFSRPQSXGD --------
    if (fnmatch.fnmatch(cell_name, "SDFSRPQSXGD*") and
            constr_pin == "Q" and constr_pin_dir == "fall" and
            rel_pin == "CP" and rel_pin_dir == "rise" and
            "!CD&SDN&!SE&!SI" in when):
        return "delay/hack/template__SDFSRPQSXGD_inpin_rise_delay_fall.sp"

    # -------- OR4D --------
    if (fnmatch.fnmatch(cell_name, "OR4D*") and
            constr_pin == "Z" and constr_pin_dir == "fall" and
            rel_pin == "A2" and rel_pin_dir == "fall"):
        return "delay/template__OR4D_inpin_fall_delay_fall.sp"

    # -------- DELED --------
    if (fnmatch.fnmatch(cell_name, "DELED*") and
            constr_pin == "Z" and constr_pin_dir == "fall" and
            rel_pin == "I" and rel_pin_dir == "fall"):
        return "delay/hack/template__DELED_inpin_fall_delay_fall.sp"

    # -------- MUX4D --------
    if (fnmatch.fnmatch(cell_name, "MUX4D*") and
            constr_pin == "Z" and constr_pin_dir == "fall" and
            rel_pin == "S1" and rel_pin_dir == "rise" and
            "I0&!I1&I2&I3&!S0" in when):
        return "delay/hack/template__MUX40PTD_inpin_rise_delay_fall.sp"

    # -------- AN4D --------
    if (fnmatch.fnmatch(cell_name, "AN4D*") and
            constr_pin == "Z" and constr_pin_dir == "rise" and
            rel_pin == "A1" and rel_pin_dir == "rise"):
        return "delay/template__AN4D_inpin_rise_delay_rise.sp"

    # -------- FA1OPTSD --------
    if (fnmatch.fnmatch(cell_name, "FA1D*") and
            constr_pin == "CO" and constr_pin_dir == "rise" and
            rel_pin == "A" and rel_pin_dir == "rise" and
            "B&!CI" in when):
        return "delay/template__FA1OPTSD_inpin_rise_delay_rise.sp"

    # -------- OAI222D --------
    if (fnmatch.fnmatch(cell_name, "OAI222D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "A2" and rel_pin_dir == "rise" and
            "!A1&!B1&B2&C1&!C2" in when):
        return "delay/hack/template__OAI2220PTPBD_inpin_rise_delay_fall.sp"

    # -------- IIND4D --------
    if (fnmatch.fnmatch(cell_name, "IIND4D*") and
            constr_pin == "ZN" and constr_pin_dir == "fall" and
            rel_pin == "A1" and rel_pin_dir == "fall"):
        return "delay/template__IIND4D_inpin_fall_delay_fall.sp"

    # -------- INVD (rise case) --------
    if (fnmatch.fnmatch(cell_name, "INVD*") and
            constr_pin == "ZN" and constr_pin_dir == "rise" and
            rel_pin == "I" and rel_pin_dir == "fall"):
        # Note: this is a duplicate-ish of the one above but for rise output
        # The 2-flow/funcs.py had this as the second INVD rule
        return "delay/template__invdX__rise.sp"

    # -------- Common fallback patterns --------
    # These match any cell not caught above, based on direction pairs.
    # Pattern: delay/template_common_inpin_{rel_dir}_delay_{constr_dir}.sp
    # or: delay/template_common_{rel_dir}_{constr_dir}.sp
    common = _try_common_delay(constr_pin_dir, rel_pin_dir)
    if common:
        return common

    return None


def _try_common_delay(constr_pin_dir, rel_pin_dir):
    """Fallback: try common delay template by direction pair."""
    # Common templates observed in templates/N2P_v1.0/delay/:
    #   template_common_inpin_rise_delay_fall.sp
    #   template_common_inpin_fall_delay_rise.sp
    #   template_common_inpin_rise_delay_rise.sp  (if exists)
    #   template_common_inpin_fall_delay_fall.sp  (if exists)
    #   template_common_fall_fall.sp
    #   template_common_rise_rise.sp (if exists)
    candidates = [
        f"delay/template_common_inpin_{rel_pin_dir}_delay_{constr_pin_dir}.sp",
        f"delay/template_common_{rel_pin_dir}_{constr_pin_dir}.sp",
    ]
    # Return first candidate; caller checks file existence
    return candidates[0]
