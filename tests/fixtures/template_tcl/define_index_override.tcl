lu_table_template "hold_template_5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  constraint_template : hold_template_5x5;
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

define_index {
  cell         : DFFQ1;
  pin          : D;
  rel_pin      : CP;
  when         : "NO_CONDITION";
  index_1      ("0.3 0.6 0.9 1.2 1.5");
  index_2      ("0.08 0.12 0.16 0.20 0.24");
}
