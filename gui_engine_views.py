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
function engRenderVerdict(p1){
  document.getElementById('eng-topo-p1chip').innerHTML=engChip(p1.status);
  document.getElementById('eng-topo-verdict').textContent=p1.detail.join('\n');
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
  <div class="panel" style="flex:1;overflow:auto;">
    <div class="eng-tab-title">Audit -- v2 re-derives and checks every queued arc</div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
      <span class="fl-label">Corner</span>
      <select id="engAuditCorner" style="min-width:200px"></select>
      <button class="btn" onclick="engAudit()">Run audit on queue</button>
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
