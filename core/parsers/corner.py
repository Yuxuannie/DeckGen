"""
corner_parser.py - Parses PVT corner names into VDD and temperature values.

Examples:
    ssgnp_0p450v_m40c  -> process=ssgnp, vdd=0.450, temp=-40
    ttgnp_0p800v_25c   -> process=ttgnp, vdd=0.800, temp=25
    ffgnp_0p900v_125c  -> process=ffgnp, vdd=0.900, temp=125
    tt_0p750v_m10c     -> process=tt,    vdd=0.750, temp=-10
"""

import re


def parse_corner_name(corner_name):
    """Parse a PVT corner name string into its components.

    Supports formats like:
        ssgnp_0p450v_m40c
        tt_0p750v_25c
        ffgnp_0p900v_125c

    Args:
        corner_name: str, the corner name

    Returns:
        dict with keys: process, vdd, temperature, raw
        Returns None if parsing fails.
    """
    corner_name = corner_name.strip()
    if not corner_name:
        return None

    # Pattern: {process}_{voltage}v_{temperature}c
    # Voltage: digits with 'p' as decimal separator, ending in 'v'
    # Temperature: optional 'm' for minus, digits, ending in 'c'
    pattern = r'^([a-zA-Z]+)_(\d+p\d+)v_(m?\d+)c$'
    m = re.match(pattern, corner_name)
    if not m:
        return None

    process = m.group(1)

    # Parse voltage: 0p450 -> 0.450
    vdd_raw = m.group(2)
    vdd = vdd_raw.replace('p', '.')

    # Parse temperature: m40 -> -40, 25 -> 25
    temp_raw = m.group(3)
    if temp_raw.startswith('m'):
        temperature = '-' + temp_raw[1:]
    else:
        temperature = temp_raw

    return {
        'process': process,
        'vdd': vdd,
        'temperature': temperature,
        'raw': corner_name,
    }


def parse_corner_list(text):
    """Parse a comma or whitespace separated list of corner names.

    Args:
        text: str, e.g. "ssgnp_0p450v_m40c, ttgnp_0p800v_25c"

    Returns:
        list of parsed corner dicts
    """
    names = re.split(r'[,;\s]+', text.strip())
    results = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        parsed = parse_corner_name(name)
        if parsed:
            results.append(parsed)
    return results
