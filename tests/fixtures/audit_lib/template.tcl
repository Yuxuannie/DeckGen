* Synthetic audit fixture (ALAPI format) -- exercises every audit verdict class.
* Netlists in ./netlist/<cell>.spi are the reconstructed anchors.
*   AIOI21 -> all arcs MATCH the engine-derived region.
*   AOI22  -> A1 arc names a BLOCKED state + omits a real one -> DIVERGENCE.
*   AOAI   -> A4 arc uses an OR -when -> UNSUPPORTED-WHEN.
*   GHOST  -> declared here but has NO netlist .spi -> ERROR (isolation).

define_template -type delay \
    -index_1 {0.0019 0.5336 1.5971 3.7240 7.9962} \
    -index_2 {0.000001 0.001 0.003 0.005 0.006270} \
    delay_template_5x5

if {[ALAPI_active_cell "AIOI21"]} {
define_cell -input { A1 A2 B } -output { ZN } -pinlist { A1 A2 B ZN } \
    -delay delay_template_5x5 AIOI21
define_arc -related_pin A1 -vector {RxxF} AIOI21
define_arc -related_pin A1 -vector {FxxR} AIOI21
define_arc -related_pin A2 -vector {xRxF} AIOI21
define_arc -related_pin A2 -vector {xFxR} AIOI21
define_arc -when "!A1&!A2" -related_pin B -vector {xxRR} AIOI21
define_arc -when "!A1&!A2" -related_pin B -vector {xxFF} AIOI21
define_arc -when "!A1&A2" -related_pin B -vector {xxRR} AIOI21
define_arc -when "!A1&A2" -related_pin B -vector {xxFF} AIOI21
define_arc -when "A1&!A2" -related_pin B -vector {xxRR} AIOI21
define_arc -when "A1&!A2" -related_pin B -vector {xxFF} AIOI21
}

if {[ALAPI_active_cell "AOI22"]} {
define_cell -input { A1 A2 B1 B2 } -output { ZN } -pinlist { A1 A2 B1 B2 ZN } \
    -delay delay_template_5x5 AOI22
define_arc -when "A2&B1&B2" -related_pin A1 -vector {RxxxF} AOI22
define_arc -when "A2&!B1" -related_pin A1 -vector {RxxxF} AOI22
}

if {[ALAPI_active_cell "AOAI"]} {
define_cell -input { A1 A2 A3 A4 } -output { ZN } -pinlist { A1 A2 A3 A4 ZN } \
    -delay delay_template_5x5 AOAI
define_arc -when "A1&A2 | A3" -related_pin A4 -vector {xxxRF} AOAI
}

if {[ALAPI_active_cell "GHOST"]} {
define_cell -input { A B } -output { Z } -pinlist { A B Z } \
    -delay delay_template_5x5 GHOST
define_arc -related_pin A -vector {RxF} GHOST
}
