set_var constraint_glitch_peak 0.1
set_var constraint_delay_degrade 0.4
set_var constraint_output_load index_2

if {[string compare "DFFQ1"] constraint_output_load index_3} {
    set foo 1
}
if {[string compare "DFFQ1"] constraint_glitch_peak 0.15} {
    set foo 2
}
