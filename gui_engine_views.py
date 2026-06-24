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
    <div class="eng-tab-title">Library Audit -- the engine derives each combinational
      arc's sensitizing region from the .subckt topology and checks it against the
      kit -when (region equivalence). The value is the split: TRUST vs FLAGGED.</div>
    <div class="eng-controls">
      <div class="eng-field"><label>Corner</label>
        <select id="engCAudCorner"></select></div>
      <button class="btn btn-primary" onclick="engCombAudit()">Run library audit</button>
    </div>
    <div id="eng-caud-summary" style="margin-bottom:14px"></div>
    <div id="eng-caud-flagged"></div>
    <div id="eng-caud-trust"></div>
  </div>
</div>
"""


def comb_audit_js():
    return r"""
function engCombAuditInit(){
  engFillSelect(document.getElementById('engCAudCorner'),engCorners());
}
function caChip(st){
  var m={MATCH:'chip-pass','DIVERGENCE':'chip-fail',
         'UNSUPPORTED-WHEN':'chip-stub',ERROR:'chip-error'};
  return '<span class="eng-chip '+(m[st]||'chip-error')+'">'+st+'</span>';
}
function caStates(arr,cls){
  if(!arr||!arr.length) return '<span class="eng-mut">(none)</span>';
  return arr.map(function(s){
    return '<span class="ca-st '+(cls||'')+'">'+esc(s)+'</span>';}).join('');
}
function caRegion(states){
  if(!states||!states.length) return '<span class="eng-mut">(none)</span>';
  return states.map(function(s){
    var dir=s.out_dir?(' <span class="ca-arrow">'+
      (s.out_dir==='R'?'&#8593;':'&#8595;')+'</span>'):'';
    var sig=(s.sig&&s.sig.length)?
      (' <span class="ca-sig">['+s.sig.map(esc).join(',')+']</span>'):'';
    return '<span class="ca-st">'+esc(s.label)+dir+sig+'</span>';
  }).join(' ');
}
function caCard(r){
  var head='<summary><span>'+esc(r.cell)+'</span>'+
    '<span class="ca-arrow">'+esc(r.rel_pin)+' &#8594; '+esc(r.output||'')+'</span>'+
    caChip(r.status)+'</summary>';
  var b='<div class="ca-body">';
  b+='<div class="ca-kv"><b>kit -when</b>'+caStates(r.kit_whens)+'</div>';
  if(r.status==='ERROR'){
    b+='<div class="ca-kv"><b>error</b>'+esc(r.detail||'')+'</div></div>';
    return '<details class="ca-card" open data-st="'+r.status+'">'+head+b+'</details>';
  }
  if(r.missing&&r.missing.length)
    b+='<div class="ca-kv"><b>missing (kit omits)</b>'+caStates(r.missing,'ca-gold')+'</div>';
  if(r.extra&&r.extra.length)
    b+='<div class="ca-kv"><b>extra (kit over-claims)</b>'+caStates(r.extra,'ca-bad')+'</div>';
  b+='<div class="ca-kv"><b>SENSITIZING</b>'+caRegion(r.sensitizing)+'</div>';
  if(r.blocked&&r.blocked.length)
    b+='<div class="ca-kv"><b>BLOCKED</b>'+caRegion(r.blocked)+'</div>';
  if(r.needs_split)
    b+='<div class="ca-kv"><b>partition</b>'+
      '<span class="ca-st ca-gold">region spans &#8805;2 SIG groups</span></div>';
  b+='<div class="ca-kv"><b>detail</b>'+esc(r.detail||'')+'</div></div>';
  var open=(r.status!=='MATCH')?' open':'';
  return '<details class="ca-card"'+open+' data-st="'+r.status+'">'+head+b+'</details>';
}
function engCombAudit(){
  if(!S.node||!S.libtype){
    document.getElementById('eng-caud-summary').innerHTML=
      '<div class="eng-detail">Pick a node + lib_type in the Explore tab first.</div>';
    return;
  }
  var corner=(document.getElementById('engCAudCorner')||{}).value||'';
  var sm=document.getElementById('eng-caud-summary');
  sm.innerHTML='<div class="eng-detail">Running audit over '+esc(S.libtype)+' ...</div>';
  document.getElementById('eng-caud-flagged').innerHTML='';
  document.getElementById('eng-caud-trust').innerHTML='';
  post('/api/engine/comb_audit',{node:S.node,lib_type:S.libtype,corner:corner})
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
    var fh='<div class="ca-cohort"><div class="ca-cohort-h ca-flagged-h">'+
      'FLAGGED -- engine wants a look ('+fl.length+')</div>';
    fh+= fl.length?fl.map(caCard).join(''):
      '<div class="eng-mut">none -- engine agrees with the kit on every arc</div>';
    fh+='</div>';
    document.getElementById('eng-caud-flagged').innerHTML=fh;
    var th='<details class="ca-cohort"><summary class="ca-cohort-h">'+
      'TRUST -- MATCH ('+tr.length+'), collapsed</summary>';
    th+= tr.map(caCard).join('');
    th+='</details>';
    document.getElementById('eng-caud-trust').innerHTML=th;
  });
}
"""
