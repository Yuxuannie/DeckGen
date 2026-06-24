"""gui_engine_views.py -- presentation fragments for the showcase GUI (spec
2026-06-10). Pure strings: design-system CSS, tab markup, vanilla JS. No engine
imports. gui.py concatenates these into HTML_PAGE.
"""

CSS_TOKENS = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f0f2f5; --border:#d8dee4;
  --text:#1c2128; --text-mut:#59636e; --accent:#0a4ea3; --accent-wk:#e7eef7;
  --pass-fg:#1a7f37; --pass-bg:#dafbe1; --fail-fg:#cf222e; --fail-bg:#ffebe9;
  --stub-fg:#9a6700; --stub-bg:#fff8c5; --err-fg:#57606a; --err-bg:#eaeef2;
  --path-data:#1a7f37; --path-masked:#cf222e; --path-clock:#0a4ea3;
  --font-ui:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --r-card:6px; --r-chip:4px; --sp:4px;
}
"""

CSS_COMPONENTS = """
.eng-chip{display:inline-block;padding:1px 8px;border-radius:var(--r-chip);
  font:600 12px/1.6 var(--font-mono);}
.chip-pass{color:var(--pass-fg);background:var(--pass-bg);}
.chip-fail{color:var(--fail-fg);background:var(--fail-bg);}
.chip-stub{color:var(--stub-fg);background:var(--stub-bg);}
.chip-error{color:var(--err-fg);background:var(--err-bg);}
.chip-na{color:var(--err-fg);background:var(--err-bg);}
.eng-card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-card);padding:12px 14px;margin:0 0 12px;}
.eng-card h4{margin:0 0 8px;font:600 14px var(--font-ui);color:var(--text);}
.eng-detail{font:12px/1.6 var(--font-mono);color:var(--text-mut);
  white-space:pre-wrap;}
.eng-stat{display:inline-block;min-width:84px;padding:8px 12px;margin:0 8px 8px 0;
  border:1px solid var(--border);border-radius:var(--r-card);background:var(--surface);}
.eng-stat .n{font:600 20px var(--font-ui);color:var(--text);}
.eng-stat .l{font:11px var(--font-ui);color:var(--text-mut);text-transform:uppercase;
  letter-spacing:.04em;}
.eng-shell{display:grid;grid-template-columns:1fr 360px;gap:16px;}
.eng-canvas{border:1px solid var(--border);border-radius:var(--r-card);
  background:var(--surface);overflow:hidden;position:relative;min-height:520px;}
.eng-canvas svg{width:100%;height:100%;display:block;cursor:grab;}
.eng-legend{position:absolute;left:10px;bottom:10px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r-card);padding:8px 10px;
  font:11px var(--font-ui);color:var(--text-mut);}
.eng-legend i{display:inline-block;width:14px;height:0;border-top-width:3px;
  border-top-style:solid;margin-right:6px;vertical-align:middle;}
.eng-table{width:100%;border-collapse:collapse;font:13px var(--font-ui);}
.eng-table th{position:sticky;top:0;background:var(--surface-2);text-align:left;
  padding:6px 10px;border-bottom:1px solid var(--border);font-weight:600;}
.eng-table td{padding:6px 10px;border-bottom:1px solid var(--border);
  font-family:var(--font-mono);font-size:12px;}
.eng-row-bad{border-left:3px solid var(--fail-fg);}
.eng-tab-title{font:600 20px var(--font-ui);color:var(--text);margin:0 0 12px;}
.eng-progress{height:2px;background:var(--accent);width:0;transition:width .2s;}
"""

CSS_COMPONENTS += """
.eng-panel{padding:18px 22px;overflow:auto;}
.eng-controls{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap;margin-bottom:16px;}
.eng-field{display:flex;flex-direction:column;gap:4px;}
.eng-field label{font:600 11px var(--font-ui);color:var(--text-mut);
  text-transform:uppercase;letter-spacing:.04em;}
.eng-field select{min-width:180px;padding:6px 8px;border:1px solid var(--border);
  border-radius:var(--r-chip);background:var(--surface);font:13px var(--font-ui);color:var(--text);}
.eng-shell{display:grid;grid-template-columns:1fr 340px;gap:18px;align-items:start;}
.eng-canvas{min-height:560px;}
.eng-canvas-msg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  color:var(--text-mut);font:13px var(--font-ui);}
.eng-inspector{display:flex;flex-direction:column;gap:12px;}
.eng-card-h{font:600 13px var(--font-ui);color:var(--text);margin-bottom:8px;
  display:flex;align-items:center;gap:8px;}
.eng-obl{font:12px/1.5 var(--font-mono);color:var(--text-mut);}
.eng-bias{width:100%;border-collapse:collapse;}
.eng-bias td{padding:4px 6px;border-bottom:1px solid var(--border);font:12px var(--font-mono);}
.eng-pin{color:var(--text);font-weight:600;}
.eng-bit{display:inline-block;min-width:20px;text-align:center;border-radius:3px;
  background:var(--surface-2);padding:0 6px;}
.eng-struct{font:12px var(--font-ui);color:var(--text);display:flex;flex-direction:column;gap:6px;}
.eng-role-l{display:inline-block;min-width:54px;color:var(--text-mut);text-transform:uppercase;
  font-size:11px;letter-spacing:.03em;}
.eng-node{display:inline-block;background:var(--accent-wk);color:var(--accent);
  border-radius:3px;padding:1px 6px;margin:2px 3px 0 0;font:11px var(--font-mono);}
.eng-mut{color:var(--text-mut);font-size:12px;}
.eng-trace{font:11px/1.5 var(--font-mono);color:var(--text-mut);white-space:pre-wrap;margin:6px 0 0;}
.eng-trace-card summary{cursor:pointer;list-style:revert;}
"""

# Library-audit cohort report -- purple+gold accents (engine region/verdict view).
CSS_COMPONENTS += """
.ca-cohort{margin:0 0 18px;}
.ca-cohort-h{font:600 15px var(--font-ui);color:var(--text);margin:0 0 10px;
  display:flex;align-items:center;gap:8px;}
.ca-flagged-h{color:#5b2a86;border-left:4px solid #b8860b;padding-left:10px;}
details.ca-cohort>summary.ca-cohort-h{cursor:pointer;list-style:revert;}
.ca-card{background:var(--surface);border:1px solid var(--border);
  border-left:3px solid #5b2a86;border-radius:var(--r-card);margin:0 0 8px;}
.ca-card>summary{cursor:pointer;padding:10px 12px;font:600 13px var(--font-mono);
  display:flex;align-items:center;gap:10px;list-style:revert;}
.ca-card[data-st="MATCH"]{border-left-color:var(--pass-fg);}
.ca-card[data-st="DIVERGENCE"]{border-left-color:var(--fail-fg);}
.ca-card[data-st="UNSUPPORTED-WHEN"]{border-left-color:var(--stub-fg);}
.ca-card[data-st="ERROR"]{border-left-color:var(--err-fg);}
.ca-body{padding:0 12px 12px 14px;font:12px/1.6 var(--font-mono);color:var(--text-mut);}
.ca-kv{margin:5px 0;}
.ca-kv b{color:var(--text);font-weight:600;min-width:140px;display:inline-block;
  vertical-align:top;}
.ca-st{display:inline-block;padding:0 6px;border-radius:3px;background:var(--surface-2);
  margin:0 3px 3px 0;}
.ca-bad{background:var(--fail-bg);color:var(--fail-fg);}
.ca-gold{background:#fff8c5;color:#7a5b00;}
.ca-sig{color:#5b2a86;}
.ca-arrow{color:var(--text-mut);}
"""

# Master-detail triage workspace (audit-first redesign 2026-06-24).
CSS_COMPONENTS += """
.ca-ws{display:flex;height:calc(100vh - 240px);min-height:420px;margin-top:12px;}
.ca-list{width:320px;min-width:200px;overflow:auto;padding-right:6px;}
.ca-list h5{margin:10px 0 6px;font:700 11px var(--font-ui);letter-spacing:.05em;
  text-transform:uppercase;color:#5b2a86;}
.ca-list .trust-h{color:var(--text-mut);}
.ca-split{width:6px;cursor:col-resize;flex:0 0 auto;
  background:linear-gradient(var(--border),var(--border)) center/1px 100% no-repeat;}
.ca-split:hover{background:linear-gradient(#5b2a86,#5b2a86) center/2px 100% no-repeat;}
.ca-detail{flex:1;overflow:auto;padding-left:16px;min-width:320px;}
.ca-li{padding:7px 9px;border-radius:5px;cursor:pointer;border-left:3px solid transparent;
  font:12px var(--font-mono);display:flex;gap:8px;align-items:center;
  justify-content:space-between;}
.ca-li:hover{background:var(--surface-2);}
.ca-li.sel{background:#f3eef8;border-left-color:#5b2a86;}
.ca-d-head{font:600 15px var(--font-ui);margin:0 0 10px;display:flex;gap:10px;
  align-items:center;flex-wrap:wrap;}
.ca-d-bool{font:13px var(--font-mono);color:#5b2a86;}
.ca-d-grid{display:grid;grid-template-columns:minmax(300px,1fr) minmax(300px,1fr);
  gap:18px;align-items:start;}
.ca-card2{border:1px solid var(--border);border-radius:6px;padding:10px 12px;
  background:var(--surface);}
.ca-card2 h4{margin:0 0 8px;font:600 12px var(--font-ui);text-transform:uppercase;
  letter-spacing:.04em;color:var(--text-mut);}
.ca-stepper{display:flex;align-items:center;gap:10px;margin-bottom:8px;
  font:12px var(--font-mono);}
.ca-stepper button{cursor:pointer;border:1px solid var(--border);background:var(--surface);
  border-radius:4px;padding:2px 9px;font:13px var(--font-mono);}
.ca-svgwrap{overflow:auto;max-height:520px;border:1px solid var(--border);
  border-radius:6px;background:#fcfbfe;padding:6px;}
.ca-rt{width:100%;border-collapse:collapse;font:12px var(--font-mono);}
.ca-rt th{text-align:left;color:var(--text-mut);font-weight:600;}
.ca-rt th,.ca-rt td{padding:3px 8px;border-bottom:1px solid var(--border);}
.ca-rt .sens{color:var(--pass-fg);} .ca-rt .blk{color:var(--text-mut);}
.ca-miss{background:#fbf1d6;color:#7a5b00;font-weight:700;}
.ca-extra{background:#ffe6c2;color:#8a4500;font-weight:700;}
.ca-d-bottom{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:16px;}
.ca-raw{font:11px var(--font-mono);white-space:pre-wrap;background:var(--surface-2);
  padding:8px 10px;border-radius:5px;color:var(--text);}
.ca-empty{color:var(--text-mut);font:13px var(--font-ui);padding:40px 0;text-align:center;}
.ca-summary{font:13px/1.5 var(--font-ui);color:var(--text);background:#fbf1d6;
  border-left:4px solid #b8860b;border-radius:4px;padding:9px 12px;margin:0 0 14px;}
.ca-why{font:12px/1.5 var(--font-mono);color:#5b2a86;margin:0 0 8px;min-height:18px;}
"""

# Chrome polish (2026-06-24): purple nav identity, compact toolbar, framed panes.
CSS_COMPONENTS += """
/* the audit view is a single full-width panel, NOT the explore two-column flex
   row (.main>.panel:last-child pins width to 380px) -- override to block. */
/* full-width ONLY when this view is the active one -- the :not(.view-hidden)
   guard is essential: a bare #id{display:block!important} outranks
   .view-hidden{display:none!important} and would pin the audit view visible on
   top of every tab. */
#view-comb-audit:not(.view-hidden){display:block !important;}
#view-comb-audit>.panel{flex:none !important;min-width:0 !important;
  border-right:none;}
.tab.active{color:#5b2a86 !important;border-bottom-color:#5b2a86 !important;}
.brand{color:#5b2a86 !important;}
.ca-bar{display:flex;align-items:center;gap:10px;margin:2px 0 12px;flex-wrap:wrap;}
.ca-lbl{font:600 11px var(--font-ui);text-transform:uppercase;letter-spacing:.04em;
  color:var(--text-mut);}
.ca-sel{padding:6px 9px;border:1px solid var(--border);border-radius:5px;
  font:13px var(--font-ui);min-width:230px;background:var(--surface);}
.ca-note{font:12px/1.45 var(--font-ui);color:var(--text-mut);max-width:560px;}
.ca-note code{font:11px var(--font-mono);background:var(--surface-2);padding:0 4px;
  border-radius:3px;color:#5b2a86;}
/* frame the two panes as cards instead of bare columns */
.ca-list{border:1px solid var(--border);border-radius:8px;background:var(--surface);
  padding:8px 10px;}
.ca-detail{border:1px solid var(--border);border-radius:8px;background:var(--surface);
  padding:16px;}
.ca-split{background:transparent;}
.ca-empty{display:flex;align-items:center;justify-content:center;height:100%;
  min-height:160px;color:var(--text-mut);font:13px var(--font-ui);text-align:center;}
.eng-stat{border-radius:8px;}
"""


def topology_tab_html():
    return """
<div class="main view-hidden" id="view-topology">
  <div class="panel eng-panel">
    <div class="eng-controls">
      <div class="eng-field"><label>Cell</label>
        <select id="engTopoCell" onchange="engTopoLoadCell()"></select></div>
      <div class="eng-field"><label>Clock pin</label>
        <select id="engTopoClk" onchange="engTopology()"></select></div>
      <div class="eng-field"><label>Data pin</label>
        <select id="engTopoData" onchange="engTopology()"></select></div>
      <div class="eng-field"><label>Corner</label>
        <select id="engTopoCorner"></select></div>
      <button class="btn btn-primary" onclick="engTopology()">Analyze</button>
    </div>
    <div class="eng-shell">
      <div class="eng-canvas" id="eng-topo-canvas">
        <div class="eng-canvas-msg" id="eng-topo-empty">Select a cell to analyze its topology.</div>
        <div class="eng-legend">
          <div><i style="border-color:var(--path-data)"></i>measured data path</div>
          <div><i style="border-color:var(--path-masked);border-top-style:dashed"></i>masked scan input</div>
          <div><i style="border-color:var(--path-clock)"></i>clock</div>
        </div>
      </div>
      <aside class="eng-inspector">
        <div class="eng-card">
          <div class="eng-card-h">Sensitization (P1) <span id="eng-topo-p1chip"></span></div>
          <div class="eng-obl" id="eng-topo-obl">Pick a clock and data pin, then Analyze.</div>
        </div>
        <div class="eng-card">
          <div class="eng-card-h">Side-pin bias</div>
          <table class="eng-bias"><tbody id="eng-topo-bias"></tbody></table>
        </div>
        <div class="eng-card">
          <div class="eng-card-h">Structure (CCC)</div>
          <div class="eng-struct" id="eng-topo-struct"></div>
        </div>
        <details class="eng-card eng-trace-card">
          <summary class="eng-card-h">Stage trace</summary>
          <pre class="eng-trace" id="eng-topo-trace"></pre>
        </details>
      </aside>
    </div>
  </div>
</div>
"""


def engine_js():
    return r"""
function engChip(status){
  var m={PASS:'chip-pass',FAIL:'chip-fail',STUB:'chip-stub',
         ERROR:'chip-error',NA:'chip-na'};
  return '<span class="eng-chip '+(m[status]||'chip-error')+'">'+status+'</span>';
}
function engPanZoom(canvas){
  var svg=canvas.querySelector('svg'); if(!svg) return;
  var vb=svg.viewBox.baseVal, pan=false, sx=0, sy=0;
  if(!vb || !vb.width){ var bb=svg.getBBox();
    svg.setAttribute('viewBox','0 0 '+bb.width+' '+bb.height); vb=svg.viewBox.baseVal; }
  svg.addEventListener('mousedown',function(e){pan=true;sx=e.clientX;sy=e.clientY;
    svg.style.cursor='grabbing';});
  window.addEventListener('mouseup',function(){pan=false;svg.style.cursor='grab';});
  svg.addEventListener('mousemove',function(e){ if(!pan) return;
    var k=vb.width/svg.clientWidth;
    vb.x-=(e.clientX-sx)*k; vb.y-=(e.clientY-sy)*k; sx=e.clientX; sy=e.clientY; });
  svg.addEventListener('wheel',function(e){e.preventDefault();
    var f=e.deltaY<0?0.9:1.1; vb.x+=vb.width*(1-f)/2; vb.y+=vb.height*(1-f)/2;
    vb.width*=f; vb.height*=f;},{passive:false});
  svg.querySelectorAll('.net').forEach(function(n){
    n.addEventListener('mouseenter',function(){
      svg.querySelectorAll('.net,.edge').forEach(function(x){x.style.opacity='.35';});
      n.style.opacity='1';});
    n.addEventListener('mouseleave',function(){
      svg.querySelectorAll('.net,.edge').forEach(function(x){x.style.opacity='1';});});
  });
}
function engCellNames(){
  return (S.cells||[]).map(function(c){
    return (typeof c==='string')?c:(c.name||c.cell||c.cell_name||'');}).filter(Boolean);
}
function engCorners(){
  return (S.selCorners&&S.selCorners.size)?Array.from(S.selCorners):(S.corners||[]);
}
function engFillSelect(sel,items){
  if(!sel) return; var prev=sel.value; sel.innerHTML='';
  items.forEach(function(n){var o=document.createElement('option');
    o.value=n;o.textContent=n;sel.appendChild(o);});
  if(prev){for(var i=0;i<sel.options.length;i++){
    if(sel.options[i].value===prev){sel.selectedIndex=i;break;}}}
}
function engPinGuess(pins,kind){
  var clk=/^(CP|CLK|CK|ECK|GCK|E)$/i, dat=/^(D|SI|TI|DATA|TE)$/i;
  for(var i=0;i<pins.length;i++){if((kind==='clk'?clk:dat).test(pins[i]))return pins[i];}
  if(kind==='clk') return pins[0]||'';
  for(var j=0;j<pins.length;j++){if(pins[j]!==document.getElementById('engTopoClk').value)return pins[j];}
  return pins[0]||'';
}
function engTopoInit(){
  engFillSelect(document.getElementById('engTopoCell'),engCellNames());
  engFillSelect(document.getElementById('engTopoCorner'),engCorners());
}
function engTopoLoadCell(){
  // first call (engine defaults) just to discover the cell's pins, then re-analyze with guesses
  var cell=(document.getElementById('engTopoCell')||{}).value||'';
  var corner=(document.getElementById('engTopoCorner')||{}).value||'';
  if(!cell) return;
  post('/api/engine/topology',{node:S.node,lib_type:S.libtype,cell:cell,corner:corner})
    .then(function(d){
      var pins=d.pins||[];
      engFillSelect(document.getElementById('engTopoClk'),pins);
      engFillSelect(document.getElementById('engTopoData'),pins);
      if(pins.length){
        document.getElementById('engTopoClk').value=engPinGuess(pins,'clk');
        document.getElementById('engTopoData').value=engPinGuess(pins,'data');
      }
      engTopology();
    });
}
function engAuditInit(){
  engFillSelect(document.getElementById('engAuditCorner'),engCorners());
}
function engTopology(){
  var cell=(document.getElementById('engTopoCell')||{}).value||'';
  var clk=(document.getElementById('engTopoClk')||{}).value||'';
  var data=(document.getElementById('engTopoData')||{}).value||'';
  var corner=(document.getElementById('engTopoCorner')||{}).value||'';
  if(!cell){return;}
  post('/api/engine/topology',{node:S.node,lib_type:S.libtype,cell:cell,corner:corner,
    arc_type:'hold',rel_pin:clk||'CP',rel_dir:'rise',
    constr_pin:data||'D',constr_dir:'fall'}).then(engRenderTopo);
}
function engRenderTopo(d){
  var c=document.getElementById('eng-topo-canvas');
  var old=c.querySelector('svg'); if(old) old.remove();
  var empty=document.getElementById('eng-topo-empty'); if(empty) empty.style.display='none';
  if(d.status==='ERROR'){
    document.getElementById('eng-topo-p1chip').innerHTML=engChip('ERROR');
    document.getElementById('eng-topo-obl').textContent=d.error||'engine error';
    return;
  }
  c.insertAdjacentHTML('afterbegin',d.svg||'');
  engPanZoom(c);
  document.getElementById('eng-topo-p1chip').innerHTML=engChip(d.p1.status);
  document.getElementById('eng-topo-obl').textContent=d.obligation||'';
  // bias table
  var bt=document.getElementById('eng-topo-bias'); bt.innerHTML='';
  var biases=d.biases||{}; var keys=Object.keys(biases);
  if(!keys.length){ bt.innerHTML='<tr><td class="eng-mut" colspan="2">no side pins</td></tr>'; }
  keys.forEach(function(p){
    var v=biases[p].value; var val=(v===null||v===undefined)?'-':v;
    bt.insertAdjacentHTML('beforeend',
      '<tr><td class="eng-pin">'+p+'</td><td><span class="eng-bit">'+val+'</span></td></tr>');
  });
  // structure
  var roles=(d.ccc&&d.ccc.roles)||{}; var sh='';
  sh+='<div class="eng-mut">'+((d.ccc&&d.ccc.components)||0)+' channel-connected component(s)</div>';
  Object.keys(roles).forEach(function(r){
    sh+='<div class="eng-role"><span class="eng-role-l">'+r+'</span> '+
      roles[r].map(function(n){return '<span class="eng-node">'+n+'</span>';}).join('')+'</div>';
  });
  document.getElementById('eng-topo-struct').innerHTML=sh||'<div class="eng-mut">no storage</div>';
  document.getElementById('eng-topo-trace').textContent=(d.stage_log||[]).join('\n');
}
function engAuditArcs(){
  if((S.auditArcs||[]).length) return S.auditArcs;
  return (S.queue||[]).map(function(q){return {arc_id:q.arc_id,cell:q.cell,
    arc_type:q.arc_type,rel_pin:q.rel_pin,rel_dir:q.rel_dir,
    probe_pin:q.probe_pin,when:q.when};});
}
function engAudit(){
  var arcs=engAuditArcs();
  if(!arcs.length){ document.getElementById('eng-audit-summary').innerHTML=
    '<div class="eng-detail">No arcs queued. Add arcs in the Explore tab first.</div>';
    document.getElementById('eng-audit-rows').innerHTML=''; return; }
  var corner=(document.getElementById('engAuditCorner')||{}).value||'';
  post('/api/engine/audit',{node:S.node,lib_type:S.libtype,corner:corner,
    arcs:arcs}).then(function(d){
    var tb=document.getElementById('eng-audit-rows'); tb.innerHTML='';
    (d.rows||[]).forEach(function(r){
      var bad=(r.P1==='FAIL'||r.P1==='ERROR'||/^MISMATCH/.test(r.bias_match));
      tb.insertAdjacentHTML('beforeend','<tr'+(bad?' class="eng-row-bad"':'')+'>'+
        '<td>'+r.cell+'</td><td>'+r.arc+'</td>'+
        '<td>'+engChip(r.P1)+'</td><td>'+engChip(r.P2)+'</td><td>'+engChip(r.P3)+'</td>'+
        '<td>'+r.bias_match+'</td><td>'+r.arc_check+'</td><td>'+(r.notes||'')+'</td></tr>');
    });
    var s=d.summary||{}, h='';
    h+='<span class="eng-stat"><span class="n">'+(s.total||0)+'</span><span class="l">arcs</span></span>';
    h+='<span class="eng-stat"><span class="n">'+(s.arc_check_agree_rate||0)+'%</span><span class="l">arc agree</span></span>';
    document.getElementById('eng-audit-summary').innerHTML=h;
  });
  document.getElementById('eng-audit-csv').onclick=function(){
    window.location='/api/engine/audit_csv?node='+encodeURIComponent(S.node)+
      '&lib_type='+encodeURIComponent(S.libtype)+'&corner='+encodeURIComponent(corner)+
      '&arcs='+encodeURIComponent(engAuditArcs().map(function(a){return a.arc_id;}).join(','));
  };
}
"""


def audit_tab_html():
    return """
<div class="main view-hidden" id="view-audit">
  <div class="panel eng-panel">
    <div class="eng-tab-title">Audit -- v2 re-derives and checks every queued arc</div>
    <div class="eng-controls">
      <div class="eng-field"><label>Corner</label>
        <select id="engAuditCorner"></select></div>
      <button class="btn btn-primary" onclick="engAudit()">Run audit on queue</button>
      <button id="eng-audit-csv" class="btn">Download audit.csv</button>
    </div>
    <div id="eng-audit-summary" style="margin-bottom:12px"></div>
    <table class="eng-table"><thead><tr>
      <th>Cell</th><th>Arc</th><th>P1</th><th>P2</th><th>P3</th>
      <th>bias_match</th><th>arc_check</th><th>notes</th></tr></thead>
      <tbody id="eng-audit-rows"></tbody></table>
  </div>
</div>
"""


def comb_audit_tab_html():
    return """
<div class="main view-hidden" id="view-comb-audit">
  <div class="panel eng-panel">
    <div class="ca-bar">
      <span class="ca-lbl">Corner</span>
      <select id="engCAudCorner" class="ca-sel"></select>
      <button class="btn btn-primary" onclick="engCombAudit()">Run audit</button>
      <span class="ca-note">Engine derives each combinational arc's sensitizing
        region from the <code>.subckt</code> and checks it against the kit
        <code>-when</code>. Flagged = engine disagrees; click one to see why.</span>
    </div>
    <div id="eng-caud-summary"></div>
    <div class="ca-ws">
      <div class="ca-list" id="ca-list">
        <div class="ca-empty">Run the audit to list arcs.</div>
      </div>
      <div class="ca-split" id="ca-split"></div>
      <div class="ca-detail" id="ca-detail">
        <div class="ca-empty">Select a flagged arc on the left to inspect it.</div>
      </div>
    </div>
  </div>
</div>
"""


def comb_audit_js():
    return r"""
var CA={rendered:[],idx:0,corner:''};
function engCombAuditInit(){
  engFillSelect(document.getElementById('engCAudCorner'),engCorners());
  engSplitInit();
}
function caChip(st){
  var m={MATCH:'chip-pass','DIVERGENCE':'chip-fail',
         'UNSUPPORTED-WHEN':'chip-stub',ERROR:'chip-error'};
  return '<span class="eng-chip '+(m[st]||'chip-error')+'">'+esc(st)+'</span>';
}
function engSplitInit(){
  var sp=document.getElementById('ca-split'), list=document.getElementById('ca-list');
  if(!sp||sp._wired) return; sp._wired=true;
  var drag=false;
  sp.addEventListener('mousedown',function(e){drag=true;e.preventDefault();});
  window.addEventListener('mouseup',function(){drag=false;});
  window.addEventListener('mousemove',function(e){
    if(!drag) return;
    var x=e.clientX-list.getBoundingClientRect().left;
    if(x>160&&x<window.innerWidth-360) list.style.width=x+'px';
  });
}
function engCombAudit(){
  if(!S.node||!S.libtype){
    document.getElementById('eng-caud-summary').innerHTML=
      '<div class="eng-detail">Pick a node + lib_type in the Explore tab first.</div>';
    return;
  }
  CA.corner=(document.getElementById('engCAudCorner')||{}).value||'';
  var sm=document.getElementById('eng-caud-summary');
  sm.innerHTML='<div class="eng-detail">Running audit over '+esc(S.libtype)+' ...</div>';
  document.getElementById('ca-list').innerHTML='<div class="ca-empty">working...</div>';
  post('/api/engine/comb_audit',{node:S.node,lib_type:S.libtype,corner:CA.corner})
    .then(function(d){
    if(d.error){ sm.innerHTML='<div class="eng-detail">'+esc(d.error)+'</div>'; return; }
    var s=d.summary||{};
    function stat(n,l){return '<span class="eng-stat"><span class="n">'+(n||0)+
      '</span><span class="l">'+l+'</span></span>';}
    sm.innerHTML=stat(s.cells,'cells')+stat(s.arcs,'arcs')+stat(s.flagged,'flagged')+
      stat(s.divergence,'divergence')+stat(s.unsupported,'unsupported')+
      stat(s.error,'error')+stat(s.match,'match');
    var fl=(d.cohorts&&d.cohorts.flagged)||[];
    var tr=(d.cohorts&&d.cohorts.trust)||[];
    function row(r){
      return '<div class="ca-li" onclick="engArcPick(this,\''+esc(r.cell)+'\',\''+
        esc(r.rel_pin)+'\',\''+esc(r.output||'')+'\')">'+
        '<span>'+esc(r.cell)+' <span class="ca-arrow">'+esc(r.rel_pin)+
        '&#8594;'+esc(r.output||'')+'</span></span>'+caChip(r.status)+'</div>';
    }
    var h='<h5>Flagged ('+fl.length+')</h5>';
    h+= fl.length?fl.map(row).join(''):'<div class="eng-mut">none</div>';
    h+='<h5 class="trust-h">Trust / match ('+tr.length+')</h5>';
    h+= tr.slice(0,400).map(row).join('');
    if(tr.length>400) h+='<div class="eng-mut">... '+(tr.length-400)+' more</div>';
    document.getElementById('ca-list').innerHTML=h;
  });
}
function engArcPick(el,cell,rel,out){
  document.querySelectorAll('.ca-li').forEach(function(n){n.classList.remove('sel');});
  if(el) el.classList.add('sel');
  var dt=document.getElementById('ca-detail');
  dt.innerHTML='<div class="ca-empty">deriving '+esc(cell)+' '+esc(rel)+'...</div>';
  post('/api/engine/arc_detail',{node:S.node,lib_type:S.libtype,corner:CA.corner,
    cell:cell,rel_pin:rel,output:out}).then(function(d){engRenderDetail(d);});
}
function engRegionTable(d){
  var side=d.side_pins||[];
  var h='<table class="ca-rt"><thead><tr>';
  side.forEach(function(p){h+='<th>'+esc(p)+'</th>';});
  h+='<th>engine</th><th>kit</th><th>diff</th></tr></thead><tbody>';
  (d.region||[]).forEach(function(r){
    var dc=r.diff==='MISS'?'ca-miss':(r.diff==='EXTRA'?'ca-extra':'');
    h+='<tr class="'+dc+'">';
    side.forEach(function(p){h+='<td>'+r.side[p]+'</td>';});
    var eng=r.engine==='SENS'?('<span class="sens">SENS'+
      (r.out_dir?(r.out_dir==='R'?' &#8593;':' &#8595;'):'')+'</span>'):
      '<span class="blk">BLOCKED</span>';
    h+='<td>'+eng+'</td><td>'+esc(r.kit)+'</td><td>'+esc(r.diff||'')+'</td></tr>';
  });
  return h+'</tbody></table>';
}
function engTruthTable(d){
  var ins=d.inputs||[];
  var h='<table class="ca-rt"><thead><tr>';
  ins.forEach(function(p){h+='<th>'+esc(p)+'</th>';});
  h+='<th>'+esc(d.output)+'</th></tr></thead><tbody>';
  (d.truth_table||[]).forEach(function(r){
    h+='<tr>';
    ins.forEach(function(p){h+='<td>'+r.inputs[p]+'</td>';});
    h+='<td><b>'+(r.out===null?'x':r.out)+'</b></td></tr>';
  });
  return h+'</tbody></table>';
}
function engStep(delta){
  if(!CA.rendered.length) return;
  CA.idx=(CA.idx+delta+CA.rendered.length)%CA.rendered.length;
  engShowState();
}
function engShowState(){
  var st=CA.rendered[CA.idx]; if(!st) return;
  var diff=st.diff?(' <span class="ca-st '+(st.diff==='MISS'?'ca-miss':'ca-extra')+
    '">'+esc(st.diff)+'</span>'):'';
  document.getElementById('ca-step-label').innerHTML=
    (CA.idx+1)+'/'+CA.rendered.length+'  state '+esc(st.label)+
    ' ['+esc(st.engine)+']'+diff;
  document.getElementById('ca-d-svg').innerHTML=st.svg;
  var w=document.getElementById('ca-step-why'); if(w) w.textContent=st.why||'';
}
function engRenderDetail(d){
  var dt=document.getElementById('ca-detail');
  if(!d||d.status!=='OK'){
    dt.innerHTML='<div class="ca-empty">'+esc((d&&(d.error||d.status))||'no detail')+
      '</div>'; return;
  }
  CA.rendered=(d.topology&&d.topology.rendered)||[]; CA.idx=0;
  var v=d.verdict||{};
  var h='<div class="ca-d-head"><span>'+esc(d.cell)+'</span>'+
    '<span class="ca-arrow">'+esc(d.rel_pin)+' &#8594; '+esc(d.output)+'</span>'+
    caChip(v.status)+'<span class="ca-d-bool">'+esc(d.boolean||'')+'</span></div>';
  h+='<div class="ca-summary">'+esc(d.summary||'')+'</div>';
  h+='<div class="ca-d-grid">';
  // topology card (signature)
  h+='<div class="ca-card2"><h4>Topology -- conduction by state</h4>'+
     '<div class="ca-stepper"><button onclick="engStep(-1)">&#9664;</button>'+
     '<span id="ca-step-label"></span>'+
     '<button onclick="engStep(1)">&#9654;</button></div>'+
     '<div class="ca-why" id="ca-step-why"></div>'+
     '<div class="ca-svgwrap" id="ca-d-svg"></div>'+
     (d.topology&&d.topology.truncated?'<div class="eng-mut">states capped</div>':'')+
     '</div>';
  // region card
  h+='<div class="ca-card2"><h4>Region -- engine vs kit</h4>'+engRegionTable(d)+'</div>';
  h+='</div>';
  // bottom: truth table + kit raw
  h+='<div class="ca-d-bottom"><div class="ca-card2"><h4>Truth table</h4>'+
     engTruthTable(d)+'</div>'+
     '<div class="ca-card2"><h4>kit -when / -vector</h4><div class="ca-raw">'+
     ((d.kit_raw||[]).map(esc).join('\n')||'(none)')+'</div>'+
     '<div class="eng-mut" style="margin-top:8px">'+esc(v.detail||'')+'</div></div></div>';
  dt.innerHTML=h;
  engShowState();
}
// This script block is emitted AFTER the engine tab divs, so view-comb-audit now
// exists in the DOM -- safe to land on the audit workspace here.
if(typeof showTab==='function') showTab('comb-audit');
"""
