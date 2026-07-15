#!/usr/bin/env python3
"""prompt-coach-beta v0.44.0 — lightweight local web dashboard.

A zero-dependency (Python stdlib only) localhost server that renders the
coach's stats, mastery, rule catalog with reference URLs, and a live config
editor. It reuses config.py's data + write helpers (build_dashboard / api_set /
api_action) so there is no duplicated logic and every write goes through the
same schema validation the CLI uses.

    python3 serve.py --cwd /path/to/repo [--port 8765]

Binds 127.0.0.1 only. A top toolbar switches between sections (Stats, Mastery,
Config, Options); the Mastery section has a level TOC (L1-L6). Read the stats,
click to edit config, reset a rule's mastery — all against the same state files
the hook and CLI use.

Routes:
    GET  /              the dashboard (self-contained HTML, multi-page SPA)
    GET  /api/data      the consolidated dashboard JSON (config.build_dashboard)
    POST /api/config    {key, value, scope}  -> config.api_set
    POST /api/action    {action, ...}        -> config.api_action
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ── import the sibling config helper (which imports the analyzer) ───────────
_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_prompt_coach_config",
                                               _HERE / "config.py")
_cfg = importlib.util.module_from_spec(_spec)
sys.modules["_prompt_coach_config"] = _cfg
_spec.loader.exec_module(_cfg)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>prompt-coach dashboard</title>
<style>
  :root{ --bg:#e7edf6; --card:#ffffff; --ink:#0c1626; --muted:#465774;
         --line:#c4d0e4; --accent:#2563eb; --ok:#0e9f6e; --warn:#b45309;
         --idle:#6f83a2; }
  @media (prefers-color-scheme:dark){ :root{ --bg:#0b1220; --card:#131f33;
         --ink:#eef4fe; --muted:#96a7c2; --line:#24344e; --accent:#5b9bff;
         --ok:#35d07f; --warn:#f0a83a; --idle:#6b7e9c; } }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  /* top toolbar (sticky) */
  .toolbar{position:sticky;top:0;z-index:10;background:var(--card);
    border-bottom:1px solid var(--line);display:flex;gap:6px;align-items:center;
    padding:10px 20px;flex-wrap:wrap}
  .toolbar .brand{font-weight:600;margin-right:8px}
  .toolbar .brand small{color:var(--muted);font-weight:400;font-size:12px}
  .toolbar nav{display:flex;gap:4px;margin-left:6px}
  .toolbar nav button{background:transparent;color:var(--muted);
    border:1px solid transparent;border-radius:8px;padding:6px 14px;
    cursor:pointer;font:inherit;font-size:14px}
  .toolbar nav button.on{background:var(--accent);color:#fff}
  .toolbar .cwd{margin-left:auto;color:var(--muted);font-size:12px;
    font-family:ui-monospace,monospace;max-width:42vw;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  main{max-width:1060px;margin:0 auto;padding:22px 24px 70px}
  .page{display:none} .page.active{display:block}
  h2{font-size:15px;margin:0 0 14px}
  .tiles{display:flex;gap:12px;flex-wrap:wrap}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:14px 18px;min-width:120px}
  .tile .n{font-size:28px;font-weight:600} .tile .l{color:var(--muted);font-size:12px}
  .tile .of{font-size:16px;color:var(--muted);font-weight:400}
  .sub{font-size:12px;color:var(--muted);margin:22px 0 8px;text-transform:uppercase;
    letter-spacing:.05em} .sub .note{text-transform:none}
  .bar{display:flex;height:24px;border-radius:8px;overflow:hidden;
    border:1px solid var(--line);background:var(--bg)}
  .bar .seg{display:block;min-width:0;transition:width .3s}
  .seg-mastered,.seg-well{background:var(--ok)} .seg-prog{background:var(--accent)}
  .seg-not,.seg-untested{background:var(--idle)} .seg-barely{background:var(--warn)}
  .legend{display:flex;gap:16px;flex-wrap:wrap;margin:10px 0;font-size:13px;color:var(--muted)}
  .legend b{color:var(--ink)}
  .dot{display:inline-block;width:10px;height:10px;border-radius:3px;
    margin-right:6px;vertical-align:middle}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:14px 16px;margin-bottom:10px}
  .note{color:var(--muted);font-size:13px;margin:14px 0}
  /* mastery: TOC + tiers */
  .mlayout{display:grid;grid-template-columns:190px 1fr;gap:22px;align-items:start}
  .toc{position:sticky;top:64px}
  .toc .h{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
    color:var(--muted);margin:0 0 8px}
  .toc a{display:flex;justify-content:space-between;gap:8px;padding:6px 10px;
    border-radius:7px;color:var(--ink);text-decoration:none;font-size:13px}
  .toc a:hover{background:var(--bg)} .toc a .c{color:var(--muted)}
  @media (max-width:720px){ .mlayout{grid-template-columns:1fr}
    .toc{position:static;display:flex;flex-wrap:wrap;gap:4px}
    .toc .h{width:100%} }
  .tier{scroll-margin-top:66px} .tier h3{font-size:13px;margin:0 0 8px;color:var(--muted)}
  .rule{display:flex;gap:10px;align-items:flex-start;padding:9px 0;
    border-top:1px solid var(--line)}
  .rule:first-child{border-top:0}
  .badge{font-size:11px;padding:2px 8px;border-radius:20px;white-space:nowrap;
    border:1px solid var(--line)}
  .b-mastered{color:var(--ok);border-color:var(--ok)}
  .b-inactive{color:var(--idle)} .b-practicing{color:var(--accent);border-color:var(--accent)}
  .b-watch{color:var(--warn);border-color:var(--warn)}
  .rule .body{flex:1;min-width:0}
  .rule .name{font-weight:600} .rule .g{color:var(--muted);font-size:13px}
  .rule .catches{font-size:13.5px;margin:3px 0}
  .ex{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:5px 0;
    font-family:ui-monospace,monospace;font-size:12.5px;line-height:1.45}
  .ex-bad{color:var(--warn)} .ex-good{color:var(--ok)} .ex-arrow{color:var(--muted)}
  .cnote{margin:4px 0;font-size:12px} .cnote summary{cursor:pointer;color:var(--muted)}
  .cnote .g{margin:6px 0}
  .rule .links{margin:6px 0 0;padding-left:18px} .rule .links li{margin:3px 0}
  .rule .links a{font-size:12px;color:var(--accent)}
  .rbar{height:7px;border-radius:5px;background:var(--bg);border:1px solid var(--line);
    overflow:hidden;margin:5px 0 3px;max-width:340px}
  .rbar span{display:block;height:100%;transition:width .3s}
  button{background:var(--accent);color:#fff;border:0;border-radius:7px;
    padding:6px 11px;cursor:pointer;font:inherit;font-size:13px}
  button.ghost{background:transparent;color:var(--muted);border:1px solid var(--line)}
  .cfg{display:grid;grid-template-columns:max-content 1fr auto;gap:10px 18px;align-items:center}
  .cfg .k{font-family:ui-monospace,monospace;font-weight:600}
  .cfg .d{color:var(--muted);font-size:12px;grid-column:1/-1;margin:-6px 0 10px;
    padding-bottom:10px;border-bottom:1px solid var(--line)}
  .cfg .ctl{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .cfg .acts{display:flex;gap:6px;justify-self:end}
  .cfg .scope{font-size:11px;color:var(--muted)}
  @media (max-width:640px){ .cfg{grid-template-columns:1fr auto}
    .cfg .ctl{grid-column:1/-1} }
  input,select,textarea{background:var(--bg);color:var(--ink);
    border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit}
  .objgrid{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:flex-start}
  .objf{display:flex;flex-direction:column;gap:3px}
  .objf .objl{font-size:11px;color:var(--muted);font-family:ui-monospace,monospace;height:14px}
  .objf .ctlbox{min-height:32px;display:flex;align-items:center}
  .catnav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
  .catnav button{background:transparent;color:var(--muted);border:1px solid var(--line)}
  .catnav button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  #toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);
    background:var(--ink);color:var(--bg);padding:9px 16px;border-radius:8px;
    opacity:0;transition:opacity .2s;pointer-events:none;font-size:13px}
  #toast.show{opacity:1}
</style></head><body>
<div class="toolbar">
  <span class="brand">🧭 prompt-coach <small id="ver"></small></span>
  <nav id="nav"></nav>
  <span class="cwd" id="cwd"></span>
</div>
<main>
  <section class="page" data-page="stats">
    <h2>Stats</h2><div id="stats"></div>
  </section>
  <section class="page" data-page="mastery">
    <h2>Mastery <span class="note" id="mtot" style="font-weight:400"></span></h2>
    <div class="mlayout">
      <aside class="toc"><div class="h">Levels</div><div id="toc"></div></aside>
      <div id="mastery"></div>
    </div>
  </section>
  <section class="page" data-page="config">
    <h2>Config</h2>
    <div class="catnav" id="catnav"></div>
    <div class="card"><div class="cfg" id="config"></div></div>
  </section>
  <section class="page" data-page="options">
    <h2>Options</h2>
    <div class="card" id="options"></div>
  </section>
</main>
<div id="toast"></div>
<script>
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
let DATA=null, CAT='all', SCOPE='global';
const PAGES=[['stats','Stats'],['mastery','Mastery'],['config','Config'],['options','Options']];
const TIER={1:'fundamentals',2:'intermediate',3:'classical prompting',
  4:'goals & loops',5:'Claude-Code tool-native',6:'skill-awareness'};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtVal=v=>Array.isArray(v)?(v.length?v.join(', '):'[]'):(v&&typeof v==='object'?JSON.stringify(v):String(v));
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),1600);};

function route(){
  let p=(location.hash||'#stats').slice(1);
  if(!PAGES.some(x=>x[0]===p)) p='stats';
  $$('.page').forEach(s=>s.classList.toggle('active',s.dataset.page===p));
  $$('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.p===p));
}
function scrollTier(t){const el=document.getElementById('tier-L'+t);if(el)el.scrollIntoView({behavior:'smooth'});}

async function load(){ DATA=await (await fetch('/api/data')).json(); render(); }
async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(body)});
  const j=await r.json(); if(!j.ok){toast('⚠ '+(j.error||'failed'));} return j;
}

function render(){
  $('#ver').textContent='v'+DATA.meta.version+' · '+DATA.meta.rule_count+' rules';
  $('#cwd').textContent=DATA.meta.cwd;
  $('#nav').innerHTML=PAGES.map(([p,l])=>`<button data-p="${p}" onclick="location.hash='${p}'">${l}</button>`).join('');
  renderStats();
  $('#mtot').textContent=`(${DATA.stats.totals.mastered}/${DATA.stats.totals.all} mastered)`;
  renderMastery(); renderCatnav(); renderConfig(); renderOptions();
  route();
}

function segbar(segs,total){
  const bar=segs.map(s=>`<span class="seg ${s.cls}" style="width:${total?(s.n/total*100):0}%" title="${esc(s.label)}: ${s.n}"></span>`).join('');
  const leg=segs.map(s=>`<span><span class="dot ${s.cls}"></span>${esc(s.label)} <b>${s.n}</b>${total?` · ${Math.round(s.n/total*100)}%`:''}</span>`).join('');
  return `<div class="bar">${bar}</div><div class="legend">${leg}</div>`;
}
function renderStats(){
  const t=DATA.stats.totals, a=DATA.mastery_analysis||{};
  const mastered=t.mastered, inprog=t.in_progress, notm=t.all-mastered-inprog;
  const well=(a.well_tested||[]).length, barely=(a.barely_tested||[]).length,
        untested=(a.untested||[]).length, close=(a.close_to_mastery||[]).length;
  $('#stats').innerHTML=`
    <div class="tiles">
      <div class="tile"><div class="n">${DATA.stats.prompt_count}</div><div class="l">prompts analyzed</div></div>
      <div class="tile"><div class="n">${mastered}<span class="of">/${t.all}</span></div><div class="l">rules mastered</div></div>
      <div class="tile"><div class="n">${inprog}</div><div class="l">in progress</div></div>
      <div class="tile"><div class="n">${notm}</div><div class="l">not mastered</div></div>
    </div>
    <h3 class="sub">Rule progress</h3>
    ${segbar([
      {label:'mastered',n:mastered,cls:'seg-mastered'},
      {label:'in progress',n:inprog,cls:'seg-prog'},
      {label:'not mastered',n:notm,cls:'seg-not'}
    ],t.all)}
    <h3 class="sub">Mastery quality <span class="note">— of the ${mastered} mastered, how well-exercised</span></h3>
    ${segbar([
      {label:'well-tested',n:well,cls:'seg-well'},
      {label:'barely-tested',n:barely,cls:'seg-barely'},
      {label:'untested',n:untested,cls:'seg-untested'}
    ],mastered)}
    <div class="note">${close} close to mastery.${untested?` ⚠ ${untested} of the mastered rules are <b>untested</b> (fired 0×) — mastery by absence, not demonstration; reset them on the Mastery page to re-earn.`:''}</div>`;
}

function ruleBar(r){
  const done=r.status==='mastered', untested=done&&r.fires_total===0;
  const pct=done?100:Math.min(100,r.min_demonstrations?Math.round(r.demonstrations/r.min_demonstrations*100):0);
  const cls=untested?'seg-barely':done?'seg-mastered':(r.demonstrations>0?'seg-prog':'seg-not');
  const cap=done?(untested?'mastered · untested (0 fires)':'mastered'):`${r.demonstrations}/${r.min_demonstrations} demos`;
  return `<div class="rbar" title="${esc(cap)}"><span class="${cls}" style="width:${pct}%"></span></div>`;
}
function renderMastery(){
  const byTier={}; DATA.rules.forEach(r=>(byTier[r.tier]=byTier[r.tier]||[]).push(r));
  const tiers=Object.keys(byTier).sort();
  $('#toc').innerHTML=tiers.map(t=>`<a href="javascript:void 0" onclick="scrollTier(${t})">`
    +`<span>L${t} · ${esc(TIER[t]||'')}</span><span class="c">${byTier[t].length}</span></a>`).join('');
  $('#mastery').innerHTML=tiers.map(tier=>{
    const rows=byTier[tier].map(r=>{
      const links=[]; if(r.anthropic_url) links.push(`<a href="${esc(r.anthropic_url)}" target="_blank">Anthropic guide ↗</a>`);
      r.sources.forEach(s=>{if(s.url)links.push(`<a href="${esc(s.url)}" target="_blank">${esc(s.title)} ↗</a>`);});
      return `<div class="rule">
        <span class="badge b-${esc(r.status)}">${esc(r.status)}</span>
        <div class="body">
          <div class="name">${esc(r.name)} <span class="g">· ${esc(r.id)} · ${r.demonstrations}/${r.min_demonstrations} demos · ${r.fires_total} fires</span></div>
          ${ruleBar(r)}
          <div class="catches">${esc(r.catches||r.guidance)}</div>
          ${(r.example_bad||r.example_good)?`<div class="ex"><span class="ex-bad">✗ ${esc(r.example_bad)}</span><span class="ex-arrow">→</span><span class="ex-good">✓ ${esc(r.example_good)}</span></div>`:''}
          <details class="cnote"><summary>coach note + references</summary>
            <div class="g">${esc(r.guidance)}</div>
            ${links.length?`<ul class="links">${links.map(l=>`<li>${l}</li>`).join('')}</ul>`:''}</details>
        </div>
        <button class="ghost" onclick="resetRule('${esc(r.id)}')">reset</button>
      </div>`;
    }).join('');
    return `<div class="tier card" id="tier-L${tier}"><h3>L${tier} · ${esc(TIER[tier]||'')}</h3>${rows}</div>`;
  }).join('');
}

function renderCatnav(){
  const cats=['all',...new Set(DATA.config.map(c=>c.category))];
  $('#catnav').innerHTML=cats.map(c=>`<button class="${c===CAT?'on':''}" onclick="setCat('${c}')">${esc(c)}</button>`).join('')
    +`<span class="scope" style="margin-left:auto">write scope:
      <select onchange="SCOPE=this.value">
        <option value="global"${SCOPE==='global'?' selected':''}>global</option>
        <option value="repo"${SCOPE==='repo'?' selected':''}>repo</option></select></span>`;
}
function setCat(c){CAT=c;renderCatnav();renderConfig();}

function objKeys(c){return Object.keys(Object.assign({},c.default||{},c.value||{}));}
function objFields(c){
  const v=c.value||{}, def=c.default||{};
  return `<div class="objgrid">`+objKeys(c).map(k=>{
    const val=(k in v)?v[k]:def[k]; const id=`cfg_${c.key}__${k}`;
    let ctl;
    if(typeof val==='boolean') ctl=`<input type="checkbox" id="${id}" data-t="bool" ${val?'checked':''}>`;
    else if(typeof val==='number') ctl=`<input type="number" id="${id}" data-t="num" value="${esc(val)}" style="width:80px">`;
    else ctl=`<input type="text" id="${id}" data-t="str" value="${val==null?'':esc(val)}" placeholder="${val==null?'null':''}" style="width:130px">`;
    return `<label class="objf"><span class="objl">${esc(k)}</span><span class="ctlbox">${ctl}</span></label>`;
  }).join('')+`</div>`;
}
function control(c){
  const id='cfg_'+c.key;
  if(c.type==='bool') return `<input type="checkbox" id="${id}" ${c.value?'checked':''}>`;
  if(c.type==='int') return `<input type="number" id="${id}" value="${esc(c.value)}" style="width:90px">`;
  if(c.choices) return `<select id="${id}">`+
    c.choices.map(o=>`<option${o===c.value?' selected':''}>${esc(o)}</option>`).join('')+`</select>`;
  if(c.type==='obj') return objFields(c);
  const v = (c.type==='list[str]')?(c.value||[]).join(', '):esc(c.value);
  return `<input type="text" id="${id}" value="${esc(v)}" style="width:220px">`;
}
function readControl(c){
  if(c.type==='obj'){
    const out={};
    objKeys(c).forEach(k=>{
      const el=document.getElementById(`cfg_${c.key}__${k}`); if(!el) return;
      const t=el.dataset.t;
      out[k]= t==='bool'?el.checked : t==='num'?Number(el.value) : (el.value===''?null:el.value);
    });
    return out;
  }
  const el=document.getElementById('cfg_'+c.key);
  if(c.type==='bool') return el.checked;
  if(c.type==='int') return Number(el.value);
  if(c.type==='list[str]') return el.value.split(',').map(s=>s.trim()).filter(Boolean);
  return el.value;
}
async function commitCfg(key){
  const c=DATA.config.find(x=>x.key===key);
  const val=readControl(c); if(val===undefined) return;
  const j=await post('/api/config',{key,value:val,scope:SCOPE});
  if(j.ok){toast('saved '+key+' = '+JSON.stringify(j.resolved));await load();}
}
function renderConfig(){
  $('#config').innerHTML=DATA.config.filter(c=>CAT==='all'||c.category===CAT).map(c=>`
    <div class="k">${esc(c.key)} <span class="scope">(${esc(c.scope)})</span></div>
    <div class="ctl">${control(c)}</div>
    <div class="acts">
      <button onclick="commitCfg('${esc(c.key)}')">Save</button>
      <button class="ghost" title="reset to default" onclick="resetKey('${esc(c.key)}')">↺</button></div>
    <div class="d">${esc(c.description)} <span class="scope">· default: ${esc(fmtVal(c.default))}</span></div>`).join('');
}
function renderOptions(){
  $('#options').innerHTML=`
    <button class="ghost" onclick="if(confirm('Reset mastery for ALL rules?'))doAction({action:'mastery-reset-all'})">Reset all mastery</button>
    <button class="ghost" onclick="load()">Refresh</button>
    <a href="${esc(DATA.meta.anthropic_base_url)}" target="_blank"><button class="ghost">Anthropic prompting guide ↗</button></a>`;
}

async function resetKey(key){const j=await post('/api/action',{action:'reset-key',key,scope:SCOPE});
  if(j.ok){toast('reset '+key);await load();}}
async function resetRule(id){const j=await post('/api/action',{action:'mastery-reset',rule_id:id});
  if(j.ok){toast('mastery reset: '+id);await load();}}
async function doAction(b){const j=await post('/api/action',b);if(j.ok){toast('done');await load();}}
window.addEventListener('hashchange',route);
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    cwd = Path.cwd()

    def log_message(self, *a):  # keep the console quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path.startswith("/api/data"):
            return self._send(200, json.dumps(_cfg.build_dashboard(self.cwd)))
        self._send(404, json.dumps({"error": "not found"}))

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_POST(self):
        payload = self._read_json()
        if self.path.startswith("/api/config"):
            res = _cfg.api_set(self.cwd, payload.get("key"),
                               payload.get("value"), payload.get("scope", "global"))
            return self._send(200 if res.get("ok") else 400, json.dumps(res))
        if self.path.startswith("/api/action"):
            res = _cfg.api_action(self.cwd, payload)
            return self._send(200 if res.get("ok") else 400, json.dumps(res))
        self._send(404, json.dumps({"error": "not found"}))


def make_server(cwd: Path, port: int) -> ThreadingHTTPServer:
    Handler.cwd = cwd
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="serve", description=__doc__)
    ap.add_argument("--cwd", default=None, help="repo for repo-scoped config")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    srv = make_server(cwd, args.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"prompt-coach dashboard → {url}  (cwd: {cwd})")
    print("Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
