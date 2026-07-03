lu_table_template "delay_template_5x5" {
  variable_1 : input_net_transition;
  variable_2 : total_output_net_capacitance;
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}

define_cell "AOI22" {
  pinlist { VDD VSS A1 A2 B1 B2 ZN }
  output_pins { ZN }
  delay_template       : delay_template_5x5;
}

define_arc {
  cell         : AOI22;
  arc_type     : combinational;
  pin          : ZN;
  pin_dir      : rise;
  rel_pin      : A1;
  rel_pin_dir  : rise;
  when         : "A2&!B1&!B2";
  lit_when     : "A2_notB1_notB2";
  probe_list   : { ZN };
  vector       : "xxRxxxF";
}
