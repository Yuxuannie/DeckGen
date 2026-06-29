from core.measurement.regions import classify_line


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
