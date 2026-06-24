* Multi-output audit fixture: half-adder HA with outputs S (=A^B) and C (=A&B).
* The audit must use each arc's -vector to assign the right output:
*   A -> S  ({RxRx}: S toggles) -- unconditional (A flips S for all B)  -> MATCH
*   A -> C  ({RxxR}: C toggles) -- kit -when "B"; engine region {B}      -> MATCH
* Netlist reused from ./netlist/HA.spi.

define_template -type delay \
    -index_1 {0.0019 0.5336 1.5971 3.7240 7.9962} \
    -index_2 {0.000001 0.001 0.003 0.005 0.006270} \
    delay_template_5x5

if {[ALAPI_active_cell "HA"]} {
define_cell -input { A B } -output { S C } -pinlist { A B S C } \
    -delay delay_template_5x5 HA
define_arc -related_pin A -vector {RxRx} HA
define_arc -when "B" -related_pin A -vector {RxxR} HA
}
