# Example ALAPI template.tcl (one inverter, two combinational arcs).
# Mirror this structure with your real cells: each cell is wrapped in an
# ALAPI_active_cell block with a define_cell and one define_arc per edge.
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
