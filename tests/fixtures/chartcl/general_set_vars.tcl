# General variant fixture
set_var constraint_glitch_peak 0.1
set_var constraint_output_load index_2
set_var -stage variation constraint_delay_degrade 0.4
# extra noise lines below must not break early-exit
set_var some_unrelated_var 99
