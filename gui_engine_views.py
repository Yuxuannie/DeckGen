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


def topology_tab_html():
    return """
<div class="main view-hidden" id="view-topology">
  <div class="panel" style="flex:1;overflow:auto;">
    <div class="eng-tab-title">Topology -- name-blind transistor analysis</div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
      <span class="fl-label">Cell</span>
      <select id="engTopoCell" style="min-width:240px" onchange="engTopology()"></select>
      <span class="fl-label">Corner</span>
      <select id="engTopoCorner" style="min-width:200px"></select>
      <button class="btn" onclick="engTopology()">Render</button>
    </div>
    <div class="eng-shell">
      <div class="eng-canvas" id="eng-topo-canvas">
        <div class="eng-legend">
          <div><i style="border-color:var(--path-data)"></i>measured data path</div>
          <div><i style="border-color:var(--path-masked);border-top-style:dashed"></i>masked scan input</div>
          <div><i style="border-color:var(--path-clock)"></i>clock</div>
        </div>
      </div>
      <div>
        <div class="eng-card"><h4>P1 -- Sensitization <span id="eng-topo-p1chip"></span></h4>
          <div class="eng-detail" id="eng-topo-verdict">Select a cell and click Render.</div></div>
        <div class="eng-card"><h4>Stage trace</h4>
          <div class="eng-detail" id="eng-topo-trace"></div></div>
        <div class="eng-card"><h4>CCC</h4>
          <div class="eng-detail" id="eng-topo-ccc"></div></div>
      </div>
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
function engTopoInit(){
  engFillSelect(document.getElementById('engTopoCell'),engCellNames());
  engFillSelect(document.getElementById('engTopoCorner'),engCorners());
}
function engAuditInit(){
  engFillSelect(document.getElementById('engAuditCorner'),engCorners());
}
function engTopology(){
  var cell=(document.getElementById('engTopoCell')||{}).value||'';
  var corner=(document.getElementById('engTopoCorner')||{}).value||'';
  if(!cell){ document.getElementById('eng-topo-verdict').textContent=
    'Select a cell (the dropdown is populated from the cells loaded in Explore).'; return; }
  var b={node:S.node,lib_type:S.libtype,cell:cell,corner:corner};
  post('/api/engine/topology',b).then(function(d){
    var c=document.getElementById('eng-topo-canvas');
    var old=c.querySelector('svg'); if(old) old.remove();
    if(d.status==='ERROR'){ c.insertAdjacentHTML('afterbegin',
      '<div class="eng-card chip-error" style="margin:16px">'+
      (d.error||'engine error')+'</div>'); return; }
    c.insertAdjacentHTML('afterbegin',d.svg);
    engPanZoom(c);
    engRenderVerdict(d.p1);
    document.getElementById('eng-topo-trace').textContent=(d.stage_log||[]).join('\n');
    document.getElementById('eng-topo-ccc').textContent=
      'components: '+d.ccc.components+'\nroles: '+JSON.stringify(d.ccc.roles);
  });
}
function engAuditArcIds(){
  // The Explore queue holds arc OBJECTS; the audit API wants arc-id STRINGS.
  if((S.auditArcs||[]).length) return S.auditArcs;
  return (S.queue||[]).map(function(q){return q.arc_id;}).filter(Boolean);
}
function engAudit(){
  var arcs=engAuditArcIds();
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
      '&arcs='+encodeURIComponent(engAuditArcIds().join(','));
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
