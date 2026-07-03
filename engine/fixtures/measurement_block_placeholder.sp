* PLACEHOLDER measurement block.
* Owned by Liberate; the engine passes it through UNCHANGED (spec SS2, SS5 Stage 4).
* The engine POSITIONS this block in the deck; it never authors or edits it.
* Replace with the real measurement block in SEGMENT 2.
.measure tran hold_cp_d trig v(CP) val='vdd/2' rise=1 targ v(D) val='vdd/2' fall=1
