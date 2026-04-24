lu_table_template "delay_template_5x5" {
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  delay_template : delay_template_5x5;
}

define_arc {
  cell : DFFQ1; arc_type : combinational;
  pin : Q; pin_dir : rise;
  rel_pin : CP; rel_pin_dir : rise;
  when : "NO_CONDITION"; lit_when : "NO_CONDITION";
  probe_list : { Q };
  vector : "RxxRxx";
}
