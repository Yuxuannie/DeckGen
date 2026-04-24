lu_table_template "hold_template_5x5" {
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
  arc_type     : setup;
  pin          : D;
  pin_dir      : rise;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
  metric       : glitch;
  metric_thresh : "0.55";
}
