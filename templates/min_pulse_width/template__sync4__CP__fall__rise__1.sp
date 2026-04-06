** SPICE Deck created by TSMC ADC Timing Team ***
* DONT_TOUCH_PINS
$HEADER_INFO
 
 
* THANOS Headers
* CONSTR_CRITERIA | pushout
* OPT_RESULTS | cp2q_del1
* MEAS_DEGRADE_PER cp2q_del1 | $PUSHOUT_PER
* CONSTR_PIN_PARAM | constr_pin_offset
 
 
* SPICE options
.options runlvl=6 ACCURATE=1 BRIEF=1 MODSRH=1 gmindc=1e-15 gdcpath=1e-15 method=gear converge=100 pode_check=0 autostop post=0 NOMOD=1 MEASDGT=7 measform=1 measfile=1 statfl=1 MCBRIEF=5 sampling_method=lhs
.save level=none
 
* Waveform
.inc '/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/std_wv_c651.spi'
.inc '$WAVEFORM_FILE'
 
* Model include file
.inc '$INCLUDE_FILE'
 
* Netlist path
.inc '$NETLIST_PATH'
 
* Library information
.param vdd_value = '$VDD_VALUE'
.param vss_value = 0
.temp $TEMPERATURE
 
* Slew and load information
.param cl = '$OUTPUT_LOAD'
.param rel_pin_slew = '$INDEX_2_VALUE'
.param constr_pin_slew = '$INDEX_1_VALUE'
 
* Voltage
VVDD VDD 0 'vdd_value'
VVSS VSS 0 'vss_value'
VVPP VPP 0 'vdd_value'
VVBB VBB 0 'vss_value'
 
* Output Load
 
* Subckt Definition
X1 $NETLIST_PINS $CELL_NAME
 
* Waveform timestamps
.param max_slew = '0.1u'
.param search_window = '$MAX_SLEW'
.param constrained_pin_t01 = '0 * max_slew'
.param constrained_pin_t02 = '16 * max_slew'
.param related_pin_t01 = '1 * max_slew'
.param related_pin_t02 = '11 * max_slew'
.param related_pin_t03 = '21 * max_slew'
.param related_pin_t04 = '31 * max_slew'
.param related_pin_t05 = '41 * max_slew'
.param related_pin_t06 = '51 * max_slew'
.param related_pin_t07 = '61 * max_slew'
.param related_pin_t08 = '71 * max_slew'
.param related_pin_t09 = '81 * max_slew'
.param related_pin_t10 = '81 * max_slew + constr_pin_offset'
.param related_pin_t11 = '101 * max_slew'
.param related_pin_t12 = '111 * max_slew'
.param related_pin_t13 = '121 * max_slew'
.param related_pin_t14 = '131 * max_slew'
.param related_pin_t15 = '141 * max_slew'
* Optimization settings
.param opt_init = '5 * search_window'
.param opt_ub = '10 * search_window'
.param opt_lb = '0 * search_window'
.param constr_pin_offset = opt_init
*.param constr_pin_offset = OPT1('opt_init', 'opt_lb', 'opt_ub')
* [1ps tolerance] relin = 0.001 / (opt_ub - opt_lb)
*.MODEL optmod opt METHOD=passfail itropt=100 absin='0.1p'
 
* Pin definitions
.option ptran_nodeset=1
.nodeset v(X1.ml*_a) = 'vdd_value'
.nodeset v(X1.sl*_a) = 'vdd_value'
.nodeset v(X1.bl*_a) = 'vdd_value'
.nodeset v(X1.ml*_b) = 'vdd_value'
.nodeset v(X1.sl*_b) = 'vdd_value'
.nodeset v(X1.bl*_b) = 'vdd_value'
.nodeset v(X1.ml*_ax) = 'vss_value'
.nodeset v(X1.sl*_ax) = 'vss_value'
.nodeset v(X1.bl*_ax) = 'vss_value'
.nodeset v(X1.ml*_bx) = 'vss_value'
.nodeset v(X1.sl*_bx) = 'vss_value'
.nodeset v(X1.bl*_bx) = 'vss_value'
.nodeset v(Q*) = 'vdd_value'
.nodeset v(QN*) = 'vss_value'
.nodeset v(Z*) = 'vdd_value'
.nodeset v(ZN*) = 'vss_value'
 
* Toggling pins
XV$REL_PIN $REL_PIN 0 stdvs_mpw_fall_rise_fall_rise_fall_rise_fall_rise_fall_rise_fall_rise_fall_rise_fall VDD='vdd_value' slew='rel_pin_slew' t01='related_pin_t01' t02='related_pin_t02' t03='related_pin_t03' t04='related_pin_t04' t05='related_pin_t05' t06='related_pin_t06' t07='related_pin_t07' t08='related_pin_t08' t09='related_pin_t09' t10='related_pin_t10' t11='related_pin_t11' t12='related_pin_t12' t13='related_pin_t13' t14='related_pin_t14' t15='related_pin_t15'
 
* Measurements
.meas cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=10 targ v(Q)  td='related_pin_t09' val='vdd_value/2' cross=1
.meas cp2cp trig v($REL_PIN) val='vdd_value/2' cross=9 targ v($CONSTR_PIN) val='vdd_value/2' cross=10
 
 
* Transient Sim Command
.tran 1p 50u sweep monte=1
 
.end
 
