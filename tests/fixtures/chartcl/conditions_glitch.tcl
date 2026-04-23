if {[string compare "CELLA"] constraint_glitch_peak 0.05} {
    set foo 1
}
if {[string compare "CELLB"] constraint_glitch_peak 0.1} {
    set foo 2
}
if {[string compare "CELLC"] constraint_glitch_peak 1e-3} {
    set foo 3
}
