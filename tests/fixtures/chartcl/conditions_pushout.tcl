if {[string compare "DFFQ1"] constraint_delay_degrade 0.25} {
    set foo 1
}
if {[string compare "SYNC2DFF"] constraint_delay_degrade 0.5} {
    set foo 2
}
