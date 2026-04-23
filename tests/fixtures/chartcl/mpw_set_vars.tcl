# MPW variant fixture: parser iterates forward, stops at sentinel
set_var constraint_glitch_peak 0.05
set_var constraint_delay_degrade 0.3
set_var constraint_output_load index_1
set_var mpw_input_threshold 0.5
# sentinel halts parsing
# cell setting depend on something below
set_var this_must_be_ignored 123
