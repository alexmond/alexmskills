#!/usr/bin/env python3
"""Optional integration test: installed Codex + local mock Responses server.

No credentials or model tokens are used. Config, hook trust bypass, transcripts,
and coach state are isolated in a temporary directory. Only our reviewed test
hook runs; this does not enable or trust any hooks in the user's installation.
Run explicitly with `make test-coach-codex` (requires Codex and local sockets).
"""
import http.server, json, os, pathlib, subprocess, tempfile, threading
import shutil as _shutil, sys as _sys
# Optional test: without an installed Codex CLI there is nothing to exercise.
# Skip loudly instead of dying on FileNotFoundError, so a machine without Codex
# gets a clear message rather than a traceback that reads like a regression.
if _shutil.which("codex") is None:
    print("SKIP: codex CLI not on PATH — this optional test needs an installed Codex")
    _sys.exit(0)
SOURCE = pathlib.Path(__file__).resolve().parent / 'analyze-prompt.py'
requests = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append(body)
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        item = {'id':'msg_probe', 'type':'message', 'role':'assistant', 'status':'completed',
                'content':[{'type':'output_text','text':'Probe complete.','annotations':[]}]}
        response = {'id':'resp_probe','object':'response','created_at':1,'model':'gpt-5.4',
                    'status':'completed','output':[item],
                    'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
        events = [
            {'type':'response.created','response':dict(response,status='in_progress',output=[])},
            {'type':'response.output_item.added','output_index':0,'item':dict(item,status='in_progress',content=[])},
            {'type':'response.output_text.delta','item_id':'msg_probe','output_index':0,'content_index':0,'delta':'Probe complete.'},
            {'type':'response.output_item.done','output_index':0,'item':item},
            {'type':'response.completed','response':response},
        ]
        for event in events:
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode())
        self.wfile.flush()
with tempfile.TemporaryDirectory(prefix='codex-coach-live-') as tmp:
    root = pathlib.Path(tmp); home=root/'codex';home.mkdir();repo=root/'repo';repo.mkdir()
    plugin=root/'plugin with spaces'
    wrapper=plugin/'scripts'/'analyze-prompt.py'
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text('''import importlib.util,sys,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('coach_probe', %r)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.GLOBAL_DIR=Path(%r);m.GLOBAL_STATE=m.GLOBAL_DIR/'state.json';m.GLOBAL_CONFIG=m.GLOBAL_DIR/'config.json'
m._CLAUDE_PROJECTS_DIR=Path(%r)
raw=sys.stdin.read();Path(%r).write_text(raw)
import io
sys.stdin=io.StringIO(raw)
sys.exit(m.main())
''' % (str(SOURCE),str(root/'state'),str(root/'no-claude'),str(root/'hook-input.json')))
    server=http.server.HTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    (home/'config.toml').write_text('''model = "gpt-5.4"
model_provider = "probe"
[model_providers.probe]
name = "Local test server"
base_url = "http://127.0.0.1:%d/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''' % server.server_port)
    # Exercise the shipped handler and its quoting, with only state redirected.
    (home/'hooks.json').write_text((SOURCE.parent.parent/'hooks/codex.json').read_text())
    env=dict(os.environ,CODEX_HOME=str(home),PLUGIN_ROOT=str(plugin))
    try:
        result=subprocess.run(['codex','--dangerously-bypass-hook-trust','exec','--skip-git-repo-check',
            '--ephemeral','--json','-C',str(repo),'Fix the bug in the login page.'],
            env=env,capture_output=True,text=True,timeout=45)
        print('Codex exit:',result.returncode)
        receipt=root/'hook-input.json'
        print('Actual hook invoked:',receipt.exists())
        if receipt.exists():
            print('Hook input fields:', sorted(json.loads(receipt.read_text())))
        injected=any('prompt-coach v' in json.dumps(r.get('input')) for r in requests)
        print('Coaching reached model request:',injected)
        print('Local model requests:',len(requests))
        if result.returncode or not injected:
            print(result.stdout[-1800:]);print(result.stderr[-1800:])
        assert result.returncode == 0 and injected
    finally:
        server.shutdown()
