lu_table_template "delay_template_5x5" {
  variable_1 : input_net_transition;
  variable_2 : total_output_net_capacitance;
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}

lu_table_template "hold_template_5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q SE SI }
  output_pins { Q }
  delay_template       : delay_template_5x5;
  constraint_template  : hold_template_5x5;
  mpw_template         : delay_template_5x5;
}

define_arc {
  cell         : DFFQ1;
  arc_type     : combinational;
  pin          : Q;
  pin_dir      : rise;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "!SE&SI";
  lit_when     : "notSE_SI";
  probe_list   : { Q };
  vector       : "RxxRxx";
}

define_arc {
  cell         : DFFQ1;
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
