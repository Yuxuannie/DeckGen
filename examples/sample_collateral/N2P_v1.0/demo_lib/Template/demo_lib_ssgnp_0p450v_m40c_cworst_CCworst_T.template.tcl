# Example ALAPI template.tcl (one inverter, two combinational arcs).
# Mirror this structure with your real cells: each cell is wrapped in an
# ALAPI_active_cell block with a define_cell and one define_arc per edge.

# The lookup table for the delay template: index_1 = input slews,
# index_2 = output loads. The nominal point (i1=i2=1) drives the deck's
# rel_pin_slew / cl params.
define_template delay_template 8x8_8P7_1065 \
  -index_1 { 0.0015 0.0030 0.0060 0.0120 0.0240 0.0480 0.0960 0.1920 } \
  -index_2 { 0.0003 0.0006 0.0012 0.0024 0.0048 0.0096 0.0192 0.0384 }

if {[ALAPI_active_cell "INVD1"]} {
  define_cell \
    -output { ZN } \
    -pinlist { I ZN } \
    -delay 8x8_8P7_1065 \
  INVD1

  define_leakage -when {!I ZN}  INVD1
  define_leakage -when {I !ZN}  INVD1

  define_arc \
    -vector {FR} \
    -related_pin I \
    -pin ZN \
  INVD1

  define_arc \
    -vector {RF} \
    -related_pin I \
    -pin ZN \
  INVD1
}

# A 2:1 mux (Z = (!S & I0) | (S & I1)). A multi-input cell with WHEN side-pin
# conditions: each data-input arc holds the select (and enumerates the other,
# masked, data input); the select arc requires the two data inputs to differ.
# Arcs transcribed from the real cell's template.tcl. pinlist order I0 I1 S Z.
define_template delay_template 8x8_0P7_1238 \
  -index_1 { 0.0015 0.0030 0.0060 0.0120 0.0240 0.0480 0.0960 0.1920 } \
  -index_2 { 0.0003 0.0006 0.0012 0.0024 0.0048 0.0096 0.0192 0.0384 }

if {[ALAPI_active_cell "MUX2MDLIMZD0P7BWP130HPNPN3P48CPD"]} {
  define_cell \
    -input { I0 I1 S } \
    -output { Z } \
    -pinlist { I0 I1 S Z } \
    -delay 8x8_0P7_1238 \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I1&!S" \
    -vector {RxxR} \
    -related_pin I0 \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I1&!S" \
    -vector {FxxF} \
    -related_pin I0 \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I0&S" \
    -vector {xRxR} \
    -related_pin I1 \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I0&S" \
    -vector {xFxF} \
    -related_pin I1 \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I0&I1" \
    -vector {xxRR} \
    -related_pin S \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD

  define_arc \
    -when "!I0&I1" \
    -vector {xxFF} \
    -related_pin S \
    -pin Z \
  MUX2MDLIMZD0P7BWP130HPNPN3P48CPD
}
