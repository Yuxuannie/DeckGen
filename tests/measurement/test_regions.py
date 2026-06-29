import os
from core.measurement.regions import classify_line, extract_recipe

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DELAY = os.path.join(_REPO, "templates/N2P_v1.0/delay/template_common_inpin_rise_delay_fall.sp")
_MPW = os.path.join(_REPO, "templates/N2P_v1.0/mpw/template__CP__syncx__D__fall__rise__1.sp")


def test_extract_recipe_delay():
    recipe = extract_recipe(open(_DELAY).read())
    assert any(".meas tran meas_delay" in l for l in recipe)
    assert any(".tran 1p 5000n" in l for l in recipe)
    assert any("stdvs_rise" in l for l in recipe)
    # collateral excluded
    assert not any(l.strip().startswith(".inc") for l in recipe)
    assert not any(l.strip().startswith("X1 ") for l in recipe)
    assert not any("vdd_value = " in l for l in recipe)


def test_extract_recipe_mpw_has_init_block():
    recipe = extract_recipe(open(_MPW).read())
    assert any(".option ptran_nodeset" in l for l in recipe)
    assert any(".nodeset v(X1.ml*_a)" in l for l in recipe)
    assert any("cp2q_del1" in l for l in recipe)
    assert any("constr_pin_offset" in l for l in recipe)
    # collateral still excluded
    assert not any(l.strip().startswith(".inc") for l in recipe)


def test_classify_collateral_lines():
    assert classify_line(".inc '$NETLIST_PATH'") == "collateral"
    assert classify_line(".temp $TEMPERATURE") == "collateral"
    assert classify_line(".param vdd_value = '$VDD_VALUE'") == "collateral"
    assert classify_line(".param cl = '$OUTPUT_LOAD'") == "collateral"
    assert classify_line("VVDD VDD 0 'vdd_value'") == "collateral"
    assert classify_line("X1 $NETLIST_PINS $CELL_NAME") == "collateral"


def test_classify_recipe_lines():
    assert classify_line(".options runlvl=6 ACCURATE=1") == "recipe"
    assert classify_line(".param related_pin_t01 = '10 * max_slew'") == "recipe"
    assert classify_line(".param max_slew = '0.1u'") == "recipe"
    assert classify_line(".option ptran_nodeset=1") == "recipe"
    assert classify_line(".nodeset v(X1.ml*_a) = 'vdd_value'") == "recipe"
    assert classify_line("XV$REL_PIN $REL_PIN 0 stdvs_rise VDD='vdd_value'") == "recipe"
    assert classify_line(".meas tran meas_delay trig v($REL_PIN) val='vdd_value/2'") == "recipe"
    assert classify_line(".tran 1p 5000n sweep monte=1") == "recipe"


def test_classify_bias_and_blank():
    assert classify_line("* Unspecified pins") == "bias"
    assert classify_line("* Pin definitions") == "bias"
    assert classify_line("") == "blank"
    assert classify_line("   ") == "blank"
