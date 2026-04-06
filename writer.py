"""
writer.py - Writes generated SPICE decks to files.

Handles:
  - Output directory creation
  - Nominal deck (nominal_sim.sp)
  - Monte Carlo deck (mc_sim.sp)
  - Deck naming convention
"""

import os


def get_deck_dirname(arc_info, when=None):
    """Generate a descriptive directory name for the deck output.

    Format: {arc_type}_{cell}_{constr_pin}_{constr_dir}_{rel_pin}_{rel_dir}_{when}
    """
    parts = [
        arc_info['ARC_TYPE'],
        arc_info['CELL_NAME'],
        arc_info.get('CONSTR_PIN', ''),
        arc_info.get('CONSTR_PIN_DIR', ''),
        arc_info['REL_PIN'],
        arc_info['REL_PIN_DIR'],
    ]
    when_str = when or 'NO_CONDITION'
    # Sanitize when condition for filesystem
    when_str = when_str.replace('!', 'not_').replace('&', '_')
    parts.append(when_str)

    return '_'.join(p for p in parts if p)


def write_deck(lines, output_path):
    """Write deck lines to a file.

    Args:
        lines: list of str, the SPICE deck content
        output_path: full path to the output file

    Returns:
        str: the path written to
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(''.join(lines))
    return output_path


def write_nominal_and_mc(nominal_lines, mc_lines, output_dir, arc_info, when=None):
    """Write both nominal and MC decks to a named subdirectory.

    Args:
        nominal_lines: list of str for nominal deck
        mc_lines: list of str for MC deck
        output_dir: base output directory
        arc_info: resolved arc info dict
        when: when condition string

    Returns:
        tuple: (nominal_path, mc_path)
    """
    dirname = get_deck_dirname(arc_info, when)
    deck_dir = os.path.join(output_dir, dirname)
    os.makedirs(deck_dir, exist_ok=True)

    nominal_path = os.path.join(deck_dir, 'nominal_sim.sp')
    mc_path = os.path.join(deck_dir, 'mc_sim.sp')

    write_deck(nominal_lines, nominal_path)
    write_deck(mc_lines, mc_path)

    return nominal_path, mc_path
