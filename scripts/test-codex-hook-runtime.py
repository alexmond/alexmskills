#!/usr/bin/env python3
"""Optional real-Codex patch hook test; local mock model, isolated trust/state."""
import http.server
import importlib.util
from unittest.mock import patch
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import shutil as _shutil, sys as _sys
# Optional test: without an installed Codex CLI there is nothing to exercise.
# Skip loudly instead of dying on FileNotFoundError, so a machine without Codex
# gets a clear message rather than a traceback that reads like a regression.
if _shutil.which("codex") is None:
    print("SKIP: codex CLI not on PATH — this optional test needs an installed Codex")
    _sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
requests = []


class Handler(http.server.BaseHTTPRequestHandler):
    patch_probe = True
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append(body)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        if self.patch_probe and len(requests) == 1:
            item = {'id':'call_patch', 'call_id':'call_patch', 'type':'custom_tool_call',
                    'name':'apply_patch', 'input':'*** Begin Patch\n*** Add File: AGENTS.md\n+- 2026-09-13 — missing topic\n*** End Patch'}
        else:
            item = {'id':'msg_done', 'type':'message', 'role':'assistant', 'status':'completed',
                    'content':[{'type':'output_text','text':'Probe complete.' if self.patch_probe else '{"ideas":[{"text":"Boundary checks"}]}','annotations':[]}]}
        response = {'id':f'resp_{len(requests)}','object':'response','created_at':1,
                    'model':'gpt-5.4','status':'completed','output':[item],
                    'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
        for event in [
            {'type':'response.created','response':dict(response,status='in_progress',output=[])},
            {'type':'response.output_item.added','output_index':0,'item':item},
            {'type':'response.output_item.done','output_index':0,'item':item},
            {'type':'response.completed','response':response},
        ]:
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode())
        self.wfile.flush()


with tempfile.TemporaryDirectory(prefix='codex-adapter-runtime-') as temp:
    root=Path(temp)
    home=root/'home'; home.mkdir()
    repo=root/'repo'; repo.mkdir()
    plugin=ROOT/'plugins/evolving-claude-md'
    server=http.server.HTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    (home/'config.toml').write_text('''model = "gpt-5.4"
model_provider = "probe"
[features]
apply_patch_freeform = true
[model_providers.probe]
name = "Local test server"
base_url = "http://127.0.0.1:%d/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''' % server.server_port)
    with (home/'config.toml').open('a') as config_file:
        config_file.write('\n[projects.'+json.dumps(str(repo))+']\ntrust_level="trusted"\n')
    config=json.loads((plugin/'hooks/codex.json').read_text())
    (home/'hooks.json').write_text(json.dumps({'hooks':{'PreToolUse':config['hooks']['PreToolUse']}}))
    try:
        result=subprocess.run(['codex','--dangerously-bypass-hook-trust','exec',
            '--skip-git-repo-check','--ephemeral','--json','--sandbox','workspace-write',
            '-C',str(repo),'Apply the requested patch.'],
            env=dict(os.environ,CODEX_HOME=str(home),PLUGIN_ROOT=str(plugin)),
            capture_output=True,text=True,timeout=45)
        denied=any('lint failed' in json.dumps(r.get('input')) for r in requests[1:])
        print('Codex exit:', result.returncode)
        print('Patch hook denial reached model:', denied)
        print('Invalid instruction file absent:', not (repo/'AGENTS.md').exists())
        if result.returncode or not denied:
            print(result.stdout[-2000:]);print(result.stderr[-2000:])
            print('Returned tool results:', json.dumps(requests[-1].get('input',[]))[-2500:] if requests else 'no request')
        assert result.returncode == 0 and denied and not (repo/'AGENTS.md').exists()
        # Test the actual mindmap runner and effective MCP config, not just argv.
        marker = root/'external-started'
        external = root/'external.py'
        external.write_text("from pathlib import Path\nPath(%r).touch()\n" % str(marker))
        project_config = repo/'.codex/config.toml'
        project_config.parent.mkdir()
        project_config.write_text('[mcp_servers."project_writer"]\ncommand="python3"\nargs=['+json.dumps(str(external))+']\n')
        with (home/'config.toml').open('a') as config_file:
            config_file.write('\n[mcp_servers.external_writer]\ncommand = "python3"\nargs = ['+json.dumps(str(external))+']\n')
        spec = importlib.util.spec_from_file_location('mindmap_probe', ROOT/'plugins/mindmap-prompt/scripts/serve.py')
        mindmap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mindmap)
        requests.clear()
        Handler.patch_probe = False
        with patch.dict(os.environ, {'CODEX_HOME':str(home)}):
            assert 'project_writer' in ' '.join(mindmap.codex_tool_config('codex', repo))
            answer, error = mindmap.run_codex('Return ideas as JSON.', repo, None)
        print('Mindmap actual Codex expansion:', bool(answer) and not error)
        print('External MCP server never started:', not marker.exists())
        assert answer == {'ideas':[{'text':'Boundary checks'}]} and not error, error
        assert not marker.exists()
        assert requests and 'external_writer' not in json.dumps(requests[-1].get('tools', []))

    finally:
        server.shutdown()
