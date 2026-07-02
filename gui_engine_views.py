"""gui_engine_views.py -- presentation fragments for the showcase GUI (spec
2026-06-10). Pure strings: design-system CSS, tab markup, vanilla JS. No engine
imports. gui.py concatenates these into HTML_PAGE.
"""

CSS_TOKENS = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f0f2f5; --border:#d8dee4;
  --text:#1c2128; --text-mut:#59636e; --accent:#5b2a86; --accent-wk:#efe7f5;
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
.ca-flagged-h{color:var(--accent);border-left:4px solid #b8860b;padding-left:10px;}
details.ca-cohort>summary.ca-cohort-h{cursor:pointer;list-style:revert;}
.ca-card{background:var(--surface);border:1px solid var(--border);
  border-left:3px solid var(--accent);border-radius:var(--r-card);margin:0 0 8px;}
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
.ca-sig{color:var(--accent);}
.ca-arrow{color:var(--text-mut);}
"""

# Master-detail triage workspace (audit-first redesign 2026-06-24).
CSS_COMPONENTS += """
.ca-ws{display:flex;height:calc(100vh - 240px);min-height:420px;margin-top:12px;}
.ca-list{width:320px;min-width:200px;overflow:auto;padding-right:6px;}
.ca-list h5{margin:10px 0 6px;font:700 11px var(--font-ui);letter-spacing:.05em;
  text-transform:uppercase;color:var(--accent);}
.ca-list .trust-h{color:var(--text-mut);}
.ca-split{width:6px;cursor:col-resize;flex:0 0 auto;
  background:linear-gradient(var(--border),var(--border)) center/1px 100% no-repeat;}
.ca-split:hover{background:linear-gradient(var(--accent),var(--accent)) center/2px 100% no-repeat;}
.ca-detail{flex:1;overflow:auto;padding-left:16px;min-width:320px;}
.ca-li{padding:7px 9px;border-radius:5px;cursor:pointer;border-left:3px solid transparent;
  font:12px var(--font-mono);display:flex;gap:8px;align-items:center;
  justify-content:space-between;}
.ca-li:hover{background:var(--surface-2);}
.ca-li.sel{background:#f3eef8;border-left-color:var(--accent);}
.ca-d-head{font:600 15px var(--font-ui);margin:0 0 10px;display:flex;gap:10px;
  align-items:center;flex-wrap:wrap;}
.ca-d-bool{font:13px var(--font-mono);color:var(--accent);}
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
.ca-why{font:12px/1.5 var(--font-mono);color:var(--accent);margin:0 0 8px;min-height:18px;}
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
.tab.active{color:var(--accent) !important;border-bottom-color:var(--accent) !important;}
.brand{color:var(--accent) !important;}
.ca-bar{display:flex;align-items:center;gap:10px;margin:2px 0 12px;flex-wrap:wrap;}
.ca-lbl{font:600 11px var(--font-ui);text-transform:uppercase;letter-spacing:.04em;
  color:var(--text-mut);}
.ca-sel{padding:6px 9px;border:1px solid var(--border);border-radius:5px;
  font:13px var(--font-ui);min-width:230px;background:var(--surface);}
.ca-note{font:12px/1.45 var(--font-ui);color:var(--text-mut);max-width:560px;}
.ca-note code{font:11px var(--font-mono);background:var(--surface-2);padding:0 4px;
  border-radius:3px;color:var(--accent);}
/* frame the two panes as cards instead of bare columns */
.ca-list{border:1px solid var(--border);border-radius:8px;background:var(--surface);
  padding:8px 10px;}
.ca-detail{border:1px solid var(--border);border-radius:8px;background:var(--surface);
  padding:16px;}
.ca-split{background:transparent;}
.ca-empty{display:flex;align-items:center;justify-content:center;height:100%;
  min-height:160px;color:var(--text-mut);font:13px var(--font-ui);text-align:center;}
.eng-stat{border-radius:8px;}
/* detail layout: compact info sidebar (region+truth+kit) | dominant topology */
.ca-detail2{display:grid;grid-template-columns:minmax(300px,380px) 1fr;gap:16px;
  align-items:start;margin-top:6px;}
.ca-side{display:flex;flex-direction:column;gap:12px;min-width:0;}
.ca-side .ca-rt{font-size:11px;}
.ca-topo-main{min-width:0;}
.ca-topo-main .ca-svgwrap{max-height:calc(100vh - 300px);height:calc(100vh - 300px);}
.ca-guide{font:12px/1.5 var(--font-ui);color:var(--text-mut);margin:0 0 8px;
  padding:7px 10px;background:var(--surface-2);border-radius:5px;}
.ca-filter{width:100%;box-sizing:border-box;padding:6px 9px;margin:0 0 8px;
  border:1px solid var(--border);border-radius:5px;font:12px var(--font-mono);
  position:sticky;top:0;background:var(--surface);z-index:1;}
.ca-more{cursor:pointer;color:var(--accent);font:600 12px var(--font-ui);padding:7px 9px;
  border-radius:5px;}
.ca-more:hover{background:#f3eef8;}
.oos-h{margin:12px 0 6px;font:700 11px var(--font-ui);letter-spacing:.05em;
  text-transform:uppercase;color:var(--text-mut);}
.ca-confirm{font:12px/1.5 var(--font-ui);color:#1a5e4a;background:#e8f6f1;
  border-left:4px solid #0a9a9a;border-radius:4px;padding:8px 11px;margin:0 0 12px;}
.ca-prog{display:flex;align-items:center;gap:12px;margin:4px 0 6px;}
.ca-prog-bar{flex:1;height:10px;background:var(--surface-2);border-radius:6px;
  overflow:hidden;}
.ca-prog-fill{height:100%;width:0;background:var(--accent);transition:width .3s;}
.ca-prog-txt{font:12px var(--font-mono);color:var(--text-mut);min-width:280px;}
.ca-log{margin:0 0 10px;max-height:120px;overflow:auto;background:#1c2128;color:#d6dae0;
  font:11px/1.5 var(--font-mono);padding:8px 10px;border-radius:6px;white-space:pre-wrap;}
"""

CSS_COMPONENTS += """
/* Phase C-2 Run/Report tab: full-width panel like the audit view. */
#view-run:not(.view-hidden){display:block !important;}
#view-run>.panel{flex:none !important;min-width:0 !important;border-right:none;}
.run-card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-card);padding:10px 12px;margin:10px 0;font:13px var(--font-ui);}
.run-scope{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px 14px;margin:0 0 12px;}
.run-fld{display:flex;flex-direction:column;gap:4px;}
.run-fld>span{font:600 11px var(--font-ui);color:var(--text-mut);
  text-transform:uppercase;letter-spacing:.04em;}
.run-in{height:30px;padding:0 8px;border:1px solid var(--border);
  border-radius:var(--r-chip);background:var(--surface);
  font:13px var(--font-mono);color:var(--text);width:100%;box-sizing:border-box;}
.run-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px;}
.run-note{font:12px/1.5 var(--font-ui);color:var(--text-mut);
  max-width:620px;margin:0 0 12px;}
.run-tbl{border-collapse:collapse;margin-top:8px;width:100%;
  font:12px var(--font-mono);}
.run-tbl th,.run-tbl td{border:1px solid var(--border);padding:3px 8px;
  text-align:left;vertical-align:top;}
.run-tbl th{background:var(--surface-2);font:600 11px var(--font-ui);}
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
        <input id="ca-filter" class="ca-filter" placeholder="filter by cell / pin..."
               oninput="engRenderList()">
        <div id="ca-rows"><div class="ca-empty">Run the audit to list arcs.</div></div>
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
         'UNSUPPORTED-WHEN':'chip-stub',ERROR:'chip-error','OUT-OF-SCOPE':'chip-na'};
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
  sm.innerHTML='<div class="ca-prog"><div class="ca-prog-bar">'+
    '<div class="ca-prog-fill" id="ca-prog-fill"></div></div>'+
    '<div class="ca-prog-txt" id="ca-prog-txt">starting...</div></div>'+
    '<pre class="ca-log" id="ca-log"></pre>';
  document.getElementById('ca-rows').innerHTML='<div class="ca-empty">running...</div>';
  if(CA.poll){clearInterval(CA.poll);CA.poll=null;}
  post('/api/engine/comb_audit',{node:S.node,lib_type:S.libtype,corner:CA.corner})
    .then(function(d){
    if(!d||!d.task_id){ sm.innerHTML='<div class="eng-detail">'+
      esc((d&&d.error)||'failed to start audit')+'</div>'; return; }
    CA.task=d.task_id;
    CA.poll=setInterval(engAuditPoll,500);
    engAuditPoll();
  });
}
function engAuditPoll(){
  if(!CA.task) return;
  post('/api/engine/audit_status',{task_id:CA.task}).then(function(t){
    if(!t||t.error){ if(CA.poll){clearInterval(CA.poll);CA.poll=null;} return; }
    var pct=t.total?Math.round(100*t.progress/t.total):0;
    var fill=document.getElementById('ca-prog-fill'); if(fill) fill.style.width=pct+'%';
    var txt=document.getElementById('ca-prog-txt');
    if(txt) txt.textContent=(t.status==='running'?
      ('Auditing '+t.progress+'/'+(t.total||'?')+'  ('+pct+'%)   '+esc(t.current||'')):
      esc(t.status));
    var log=document.getElementById('ca-log');
    if(log){ log.textContent=(t.log||[]).join('\n'); log.scrollTop=log.scrollHeight; }
    if(t.status==='done'){ if(CA.poll){clearInterval(CA.poll);CA.poll=null;}
      engAuditRender(t.result); }
    else if(t.status==='error'){ if(CA.poll){clearInterval(CA.poll);CA.poll=null;}
      document.getElementById('eng-caud-summary').innerHTML=
        '<div class="eng-detail">audit error: '+esc(t.error||'')+'</div>'; }
  });
}
function engAuditRender(d){
  var s=(d&&d.summary)||{};
  function stat(n,l){return '<span class="eng-stat"><span class="n">'+(n||0)+
    '</span><span class="l">'+l+'</span></span>';}
  document.getElementById('eng-caud-summary').innerHTML=
    stat(s.cells,'cells')+stat(s.arcs,'arcs')+stat(s.flagged,'flagged')+
    stat(s.divergence,'divergence')+stat(s.unsupported,'unsupported')+
    stat(s.error,'error')+stat(s.out_of_scope,'out-of-scope')+stat(s.match,'match');
  CA.flagged=(d&&d.cohorts&&d.cohorts.flagged)||[];
  CA.trust=(d&&d.cohorts&&d.cohorts.trust)||[];
  CA.oos=(d&&d.cohorts&&d.cohorts.out_of_scope)||[];
  CA.showAllTrust=false; CA.showAllOos=false;
  engRenderList();
}
function caRow(r){
  return '<div class="ca-li" onclick="engArcPick(this,\''+esc(r.cell)+'\',\''+
    esc(r.rel_pin)+'\',\''+esc(r.output||'')+'\')">'+
    '<span>'+esc(r.cell)+' <span class="ca-arrow">'+esc(r.rel_pin)+
    '&#8594;'+esc(r.output||'')+'</span></span>'+caChip(r.status)+'</div>';
}
function engRenderList(){
  var box=document.getElementById('ca-rows'); if(!box) return;
  var q=((document.getElementById('ca-filter')||{}).value||'').toLowerCase();
  function m(r){return !q||((r.cell+' '+r.rel_pin+' '+(r.output||'')).toLowerCase().indexOf(q)>=0);}
  var fl=(CA.flagged||[]).filter(m), tr=(CA.trust||[]).filter(m), oo=(CA.oos||[]).filter(m);
  var CAP=300;
  var h='<h5>Flagged -- engine disagrees ('+fl.length+')</h5>';
  h+= fl.length?fl.map(caRow).join(''):'<div class="eng-mut">none</div>';
  var trCap=(q||CA.showAllTrust)?tr.length:Math.min(tr.length,CAP);
  h+='<h5 class="trust-h">Trust / match ('+tr.length+')</h5>';
  h+= tr.slice(0,trCap).map(caRow).join('');
  if(trCap<tr.length) h+='<div class="ca-more" onclick="CA.showAllTrust=true;engRenderList()">Show all '+tr.length+' matched &#8595;</div>';
  if(oo.length){
    var ooCap=(q||CA.showAllOos)?oo.length:Math.min(oo.length,CAP);
    h+='<h5 class="oos-h">Out of scope -- sequential / clock ('+oo.length+')</h5>';
    h+= oo.slice(0,ooCap).map(caRow).join('');
    if(ooCap<oo.length) h+='<div class="ca-more" onclick="CA.showAllOos=true;engRenderList()">Show all '+oo.length+' &#8595;</div>';
  }
  box.innerHTML=h;
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
  if(v.status==='MATCH')
    h+='<div class="ca-confirm">How to confirm this match: in the Region table every '+
       '<b>SENS</b> row shows kit=<b>covered</b> with no MISS/EXTRA, and stepping the '+
       'topology shows the pin drives the output in exactly those states (and only those).</div>';
  else if(v.status==='OUT-OF-SCOPE')
    h+='<div class="ca-confirm">Sequential cell (clock/latch): toggling the pin changes '+
       'the output only through stored state, which the combinational engine cannot '+
       'evaluate -- so this is NOT a divergence, just out of combinational scope.</div>';
  // layout: compact info sidebar on the LEFT, dominant topology on the RIGHT
  h+='<div class="ca-detail2">';
  h+='<div class="ca-side">';
  h+='<div class="ca-card2"><h4>Region -- engine vs kit</h4>'+engRegionTable(d)+'</div>';
  h+='<div class="ca-card2"><h4>Truth table</h4>'+engTruthTable(d)+'</div>';
  h+='<div class="ca-card2"><h4>kit -when / -vector</h4><div class="ca-raw">'+
     ((d.kit_raw||[]).map(esc).join('\n')||'(none)')+'</div></div>';
  h+='</div>';
  h+='<div class="ca-card2 ca-topo-main"><h4>Topology -- conduction by state</h4>'+
     '<div class="ca-guide">Read: <b>VDD</b> rail on top, <b>VSS</b> on the bottom, '+
     'the output net in the middle. <b style="color:#0a9a9a">Teal</b> = transistors '+
     'conducting in THIS state. A teal path from a rail down to the output means '+
     'the toggling pin (<b>*</b>) can drive the output here; no teal path = blocked.</div>'+
     '<div class="ca-stepper"><button onclick="engStep(-1)">&#9664;</button>'+
     '<span id="ca-step-label"></span>'+
     '<button onclick="engStep(1)">&#9654;</button></div>'+
     '<div class="ca-why" id="ca-step-why"></div>'+
     '<div class="ca-svgwrap" id="ca-d-svg"></div>'+
     (d.topology&&d.topology.truncated?'<div class="eng-mut">states capped</div>':'')+
     '</div>';
  h+='</div>';
  dt.innerHTML=h;
  engShowState();
}
// This script block is emitted AFTER the engine tab divs, so view-comb-audit now
// exists in the DOM -- safe to land on the audit workspace here.
if(typeof showTab==='function') showTab('comb-audit');
"""


def run_tab_html():
    """Phase C-2 Run/Report tab: scope -> Generate (stops) -> review coverage
    -> Submit (operator confirm gate emits bsub arrays)."""
    return """
<div class="main view-hidden" id="view-run">
  <div class="panel eng-panel">
    <div class="run-scope">
      <label class="run-fld"><span>Corner</span>
        <select id="runCorner" class="run-in"></select></label>
      <label class="run-fld"><span>Cells</span>
        <input id="runCells" class="run-in" placeholder="glob(s), blank = all">
      </label>
      <label class="run-fld"><span>Arcs per cell</span>
        <input id="runArcsN" class="run-in" placeholder="all"></label>
      <label class="run-fld"><span>Table points</span>
        <input id="runTP" class="run-in" placeholder="(1,1) (2,3), blank = all">
      </label>
      <label class="run-fld"><span>Output dir</span>
        <input id="runOut" class="run-in" placeholder="./run_output/"></label>
    </div>
    <div class="run-actions">
      <button class="btn" onclick="runPlan()">Preview scope</button>
      <button class="btn btn-primary" id="runGenerateBtn"
              onclick="runGenerate()">Generate decks</button>
      <button class="btn" id="runSubmitBtn" onclick="runSubmit()" disabled>
        Submit to LSF</button>
    </div>
    <p class="run-note">Generate builds the decks locally and stops. Review the
      coverage below, then Submit emits the bsub arrays -- nothing is queued to
      LSF until you confirm.</p>
    <div id="run-progress" style="display:none;margin:8px 0">
      <div class="ca-prog"><div class="ca-prog-bar">
        <div class="ca-prog-fill" id="run-bar-fill"></div></div></div>
      <div id="run-progress-text" class="eng-mut"></div>
    </div>
    <div id="run-summary"></div>
    <div id="run-triage"></div>
    <div id="run-lsf"></div>
  </div>
</div>
"""


def run_js():
    return r"""
var RUN={taskId:'',polling:false,outDir:''};
function runInit(){
  if(typeof engCorners==='function'&&typeof engFillSelect==='function')
    engFillSelect(document.getElementById('runCorner'),
                  ['(all corners)'].concat(engCorners()));
}
function runParseTP(s){var r=[],m,re=/\(\s*(\d+)\s*,\s*(\d+)\s*\)/g;
  while((m=re.exec(s||''))!==null)
    r.push([parseInt(m[1],10),parseInt(m[2],10)]);return r;}
function runPayload(){
  var corner=document.getElementById('runCorner').value;
  var cells=document.getElementById('runCells').value.trim();
  var arcsN=document.getElementById('runArcsN').value.trim();
  var tp=runParseTP(document.getElementById('runTP').value);
  var out=document.getElementById('runOut').value.trim()||'./run_output';
  var p={node:S.node,lib_type:S.libtype,out:out};
  if(corner&&corner.indexOf('(all')!==0)p.corners=[corner];
  if(cells)p.cells=cells.split(/[\s,]+/).filter(Boolean);
  if(arcsN)p.arcs_per_cell=parseInt(arcsN,10);
  if(tp.length)p.table_points=tp;
  return p;
}
function runErr(id,msg){document.getElementById(id).innerHTML=
  '<div class="ca-empty">'+esc(msg)+'</div>';}
function runPlan(){
  post('/api/run/plan',runPayload()).then(function(d){
    if(d.error){runErr('run-summary',d.error);return;}
    // roll up the per-(cell,corner) matrix to per-cell totals so the preview
    // stays compact even at thousands of work items.
    var byCell={},corners={};
    (d.matrix||[]).forEach(function(m){
      byCell[m.cell]=(byCell[m.cell]||0)+m.count;corners[m.corner]=1;});
    var cells=Object.keys(byCell).sort();
    var ncorn=Object.keys(corners).length;
    var rows=cells.map(function(c){return '<tr><td>'+esc(c)+
      '</td><td>'+byCell[c]+'</td></tr>';}).join('');
    // The exact arc identifiers the scope selected -- so it is visible which
    // arc is which, not just how many per cell.
    var arcs=d.arcs||[];
    var arcRows=arcs.map(function(a){return '<tr><td>'+esc(a.arc_id)+
      '</td><td>'+esc(a.corner)+'</td></tr>';}).join('');
    var arcNote=d.arcs_truncated?
      ' (showing first '+arcs.length+' of '+d.expected+')':'';
    document.getElementById('run-summary').innerHTML=
      '<div class="run-card"><b>Scope preview:</b> '+d.expected+
      ' work items across '+cells.length+' cell'+(cells.length===1?'':'s')+
      ' &times; '+ncorn+' corner'+(ncorn===1?'':'s')+
      '<div style="max-height:200px;overflow:auto;margin-top:6px">'+
      '<table class="run-tbl"><tr><th>cell</th><th>items</th></tr>'+
      rows+'</table></div>'+
      '<div style="margin-top:8px"><b>Selected arcs'+arcNote+':</b>'+
      '<div style="max-height:220px;overflow:auto;margin-top:6px">'+
      '<table class="run-tbl"><tr><th>arc_id</th><th>corner</th></tr>'+
      arcRows+'</table></div></div></div>';
  });
}
function runGenerate(){
  document.getElementById('runSubmitBtn').disabled=true;
  document.getElementById('run-triage').innerHTML='';
  document.getElementById('run-lsf').innerHTML='';
  post('/api/run/generate',runPayload()).then(function(d){
    if(d.error){runErr('run-summary',d.error);return;}
    RUN.taskId=d.task_id;
    document.getElementById('run-progress').style.display='block';
    RUN.polling=true;runPoll();
  });
}
function runPoll(){
  if(!RUN.polling)return;
  post('/api/run/status',{task_id:RUN.taskId}).then(function(d){
    var pct=d.total?Math.round(100*d.progress/d.total):0;
    document.getElementById('run-bar-fill').style.width=pct+'%';
    document.getElementById('run-progress-text').textContent=
      'Generating '+(d.progress||0)+'/'+(d.total||0)+' ('+pct+'%)'+
      (d.current?' - '+d.current:'');
    if(d.status==='running'){setTimeout(runPoll,400);return;}
    RUN.polling=false;
    RUN.outDir=d.out_dir||'';
    if(d.status==='error'){runErr('run-summary',d.error||'error');return;}
    runLoadCoverage();
    document.getElementById('runSubmitBtn').disabled=false;
  });
}
function runLoadCoverage(){
  post('/api/run/coverage',{task_id:RUN.taskId}).then(function(d){
    if(d.error)return;runRenderCoverage(d);});
}
function runRenderCoverage(d){
  var su=d.summary||{};
  var badge=su.balanced?'<span class="eng-chip chip-pass">BALANCED</span>':
    '<span class="eng-chip chip-fail">UNBALANCED</span>';
  var gen=su.generated||0;
  var loc=RUN.outDir?'<div class="eng-mut" style="margin-top:6px">Wrote '+gen+
    ' deck'+(gen===1?'':'s')+' to <code>'+esc(RUN.outDir)+'</code>.'+
    (gen===0?' No decks were generated -- see the triage table below, or '+
      '<code>ledger.ndjson</code> in that folder for the reason on every '+
      'arc.':'')+'</div>':'';
  document.getElementById('run-summary').innerHTML=
    '<div class="run-card">'+badge+' &nbsp;expected '+su.expected+
    ' = generated '+su.generated+' + submitted '+(su.submitted||0)+
    ' + error '+su.generation_error+' + skipped '+su.skipped+loc+'</div>';
  var tri=d.triage||[];
  var th=document.getElementById('run-triage');
  if(!tri.length){th.innerHTML=
    '<div class="eng-mut">No generation errors.</div>';return;}
  var body=tri.map(function(r){return '<tr><td>'+esc(r.category||'')+
    '</td><td>'+esc(r.arc_id||'')+'</td><td>'+esc(r.reason||'')+
    '</td></tr>';}).join('');
  th.innerHTML='<div class="run-card"><b>Triage ('+tri.length+
    ' generation errors)</b><table class="run-tbl"><tr><th>category</th>'+
    '<th>arc</th><th>reason</th></tr>'+body+'</table></div>';
}
function runSubmit(){
  if(!RUN.taskId)return;
  if(!confirm('Submit generated decks to LSF? This emits bsub job arrays.'))
    return;
  post('/api/run/submit',{task_id:RUN.taskId}).then(function(d){
    var el=document.getElementById('run-lsf');
    if(d.nothing_to_submit){el.innerHTML=
      '<div class="ca-empty">Nothing to submit: '+esc(d.error||'')+
      '</div>';return;}
    if(d.error){runErr('run-lsf',d.error);return;}
    if(d.coverage)runRenderCoverage(d.coverage);
    var lines=(d.bjobs||[]).map(function(l){return esc(l);}).join('<br>');
    el.innerHTML='<div class="run-card"><b>Submitted -- bsub arrays queued'+
      '</b><pre style="white-space:pre-wrap">'+lines+'</pre></div>';
    document.getElementById('runSubmitBtn').disabled=true;
  });
}
"""
