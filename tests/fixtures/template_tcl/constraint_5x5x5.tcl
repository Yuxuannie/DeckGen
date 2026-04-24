lu_table_template "constraint_5x5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  variable_3 : total_output_net_capacitance;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
  index_3 ("0.0005 0.001 0.005 0.01 0.05");
}

define_cell "DFFQ1_3D" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  constraint_template : constraint_5x5x5;
}

define_arc {
  cell         : DFFQ1_3D;
  arc_type     : hold;
  pin          : D;
  pin_dir      : fall;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
}
