*** SPICE Deck created by TSMC ADC Timing Team ***
* DONT_TOUCH_PINS
$HEADER_INFO

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
.param cl = '$INDEX_2_VALUE'
.param rel_pin_slew = '$INDEX_1_VALUE'

* Voltage
VVDD VDD 0 'vdd_value'
VVSS VSS 0 'vss_value'
VVPP VPP 0 'vdd_value'
VVBB VBB 0 'vss_value'

* Output Load
* (load cap C0 $PROBE_PIN 0 'cl' is injected by deck_builder)

* Subckt Definition
X1 $NETLIST_PINS $CELL_NAME

* Waveform timestamps
.param max_slew = '$MAX_SLEW'
.param related_pin_t01 = 200ns

* Pin definitions

* Toggling pins
XV$REL_PIN $REL_PIN 0 stdvs_fall VDD='vdd_value' slew='rel_pin_slew' t01='related_pin_t01'

* Measurements
.meas tran meas_delay trig v($REL_PIN) val='vdd_value/2' cross=1 targ v($PROBE_PIN_1) val='vdd_value/2' cross=1
.meas tran half_tt_out trig v($PROBE_PIN_1) val='vdd_value*0.3' cross=1 targ v($PROBE_PIN_1) val='vdd_value*0.7' cross=1
.meas tran tt_out param='half_tt_out*2'

* Transient Sim Command
.tran 1p 5000n

.end
