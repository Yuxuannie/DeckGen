set glitch_low_threshold 0.05
set_config_opt -type {*hold*} {
    -cell {AND2X1 AND2X2 OR2X1}
    glitch_high_threshold 0.3 0.3 0.3
}
