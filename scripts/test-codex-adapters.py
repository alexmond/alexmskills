#!/usr/bin/env python3
"""Cross-client regressions using shipped handlers, with no model calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem.replace('-', '_'), ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Adapters(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-adapter-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def hook(self, plugin, handler, event='PreToolUse', name='apply_patch', inp=None):
        payload = dict(cwd=str(self.root), hook_event_name=event, tool_name=name, tool_input=inp or {})
        proc = subprocess.run([sys.executable, str(ROOT / 'plugins' / plugin / 'hooks/codex-bridge.py'), handler],
                              input=json.dumps(payload), text=True, capture_output=True, check=True,
                              env=dict(os.environ, PROGRESS_HOME=str(self.root / "progress")))
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def test_added_agents_file_denied_but_source_allowed(self):
        for path, denied in [('AGENTS.md', True), ('AGENTS.override.md', True), ('src/example.md', False)]:
            result = self.hook('evolving-claude-md', 'skills/evolving-claude-md/lint-claude-md.py',
                               inp={'command':f'*** Begin Patch\n*** Add File: {path}\n+- 2026-09-12 — missing topic\n*** End Patch'})
            self.assertEqual(result.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny', denied)

    def test_multiple_patch_files_and_move(self):
        result = self.hook('evolving-claude-md', 'skills/evolving-claude-md/lint-claude-md.py', inp={'patch':
            '*** Begin Patch\n*** Update File: ok.py\n+x=1\n*** Update File: note.md\n*** Move to: AGENTS.md\n+- 2026-09-12 — bad\n*** End Patch'})
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_memory_contract(self):
        result = self.hook('memory-hygiene', 'skills/memory-hygiene/lint-memory-write.py', inp={'input':
            '*** Begin Patch\n*** Add File: .codex/memory/fact.md\n+yesterday it worked\n*** End Patch'})
        self.assertIn('frontmatter', result['hookSpecificOutput']['permissionDecisionReason'])
        index = self.root / '.codex/memory/MEMORY.md'
        index.parent.mkdir(parents=True)
        index.write_text('- [Testing](testing.md) — build failures\n')
        loaded = self.hook('memory-hygiene', '--memory', event='SessionStart')
        self.assertIn('testing.md', loaded['hookSpecificOutput']['additionalContext'])

    def test_crew_gate(self):
        run = self.root / '.claude/dev-crew/runs/one'
        run.mkdir(parents=True)
        args = {'message':'Act as dc-dev and implement the contract', 'task_name':'dc-dev'}
        result = self.hook('dev-crew', 'scripts/check-handoffs.py', name='spawn_agent', inp=args)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        (run/'CONTRACT.md').write_text('status: READY\n')
        self.assertEqual(self.hook('dev-crew', 'scripts/check-handoffs.py', name='spawn_agent', inp=args), {})
        (run/'CONTRACT.md').write_text('status: BLOCKED\n')
        self.assertEqual(self.hook('dev-crew', 'scripts/check-handoffs.py', name='spawn_agent', inp=args)['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_deployer_uses_target_not_mentions_and_blocks_failed_qa(self):
        run = self.root / '.claude/dev-crew/runs/one'
        run.mkdir(parents=True)
        (run/'CONTRACT.md').write_text('status: READY\n')
        (run/'QA.md').write_text('FAIL: integration tests failed\n')
        args = {'task_name':'dc-deployer', 'message':'Act as dc-deployer; dc-dev implemented this change.'}
        result = self.hook('dev-crew', 'scripts/check-handoffs.py', name='spawn_agent', inp=args)
        self.assertIn('FAIL verdict', result['hookSpecificOutput']['permissionDecisionReason'])

    def test_progress_nudge_does_not_approve(self):
        result = self.hook('progress-channel', 'hooks/suggest-progress.py',
                           name='exec_command', inp={'cmd':'mvn test'})
        output = result['hookSpecificOutput']
        self.assertNotIn('permissionDecision', output)
        self.assertIn('companion terminal', output['additionalContext'])

    def test_root_override_does_not_hide_nested_agents(self):
        (self.root/'AGENTS.override.md').write_text('# Root override\n')
        child=self.root/'child'; child.mkdir()
        (child/'AGENTS.md').write_text('# Child rules\n')
        with patch.dict(os.environ, {'SKILL_CLIENT':'codex', 'SKILL_INSTRUCTIONS_FILE':'AGENTS.override.md'}):
            audit = module('plugins/evolving-claude-md/skills/evolving-claude-md/audit-claude-md.py')
            self.assertEqual([path for path, size in audit.companion_files(str(self.root))], ['child/AGENTS.md'])
            (child/'AGENTS.override.md').write_text('# Child override\n')
            self.assertEqual([path for path, size in audit.companion_files(str(self.root))], ['child/AGENTS.override.md'])

    def test_capture_reads_codex_calls_only(self):
        capture = module('plugins/evolving-claude-md/skills/evolving-claude-md/capture-triggers.py')
        transcript = self.root / 'rollout.jsonl'
        transcript.write_text('\n'.join(json.dumps(item) for item in [
            {'type':'event_msg', 'payload':{'type':'user_message', 'message':'git commit and apply_patch'}},
            {'type':'response_item', 'payload':{'type':'function_call', 'name':'exec_command', 'arguments':'{"cmd":"git commit -m fix"}'}},
            {'type':'response_item', 'payload':{'type':'custom_tool_call', 'name':'apply_patch', 'input':'*** Update File: src/main.py\n+x=1'}},
        ]))
        with patch.dict(os.environ, {'SKILL_CLIENT':'codex', 'SKILL_INSTRUCTIONS_FILE':'AGENTS.md'}):
            activity = capture.session_activity(str(transcript))
            self.assertEqual(activity['commits'], 1)
            self.assertEqual(activity['edits'], 1)
            self.assertFalse(activity['claude_md_touched'])

    def test_claude_paths_unchanged(self):
        lint = module('plugins/evolving-claude-md/skills/evolving-claude-md/lint-claude-md.py')
        memory = module('plugins/memory-hygiene/skills/memory-hygiene/lint-memory-write.py')
        with patch.dict(os.environ, {'SKILL_CLIENT':'claude'}):
            self.assertTrue(lint.is_claude_md('CLAUDE.md'))
            self.assertFalse(lint.is_claude_md('AGENTS.md'))
            self.assertEqual(memory.memory_part('/home/example/.claude/projects/foo/memory/MEMORY.md'), 'index')
            self.assertIsNone(memory.memory_part('.codex/memory/MEMORY.md'))

    def test_progress_identity(self):
        progress = module('plugins/progress-channel/scripts/progress.py')
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'codex-one'}, clear=True):
            self.assertEqual(progress.session_identity()[0], 'codex-one')
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'codex-one', 'CLAUDE_CODE_SESSION_ID':'claude-one'}, clear=True):
            self.assertEqual(progress.session_identity()[0], 'claude-one')

    def test_mindmap_clients_and_output(self):
        server = module('plugins/mindmap-prompt/scripts/serve.py')
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'test'}, clear=True):
            self.assertEqual(server.ai_client(), 'codex')
            self.assertEqual(server.ai_client('claude'), 'claude')
        reply = '{"ideas":[{"text":"Test boundaries"}]}'
        def run(cmd, **kw):
            if 'mcp' in cmd:
                self.assertIn('plugins', cmd)
                return subprocess.CompletedProcess(cmd, 0, '[{"name":"external.writer"}]', '')
            self.assertIn('mcp_servers={"external.writer"={enabled=false}}', cmd)
            self.assertIn('plugins', cmd)
            self.assertIn('read-only', cmd)
            self.assertIn('shell_tool', cmd)
            self.assertEqual(kw['cwd'], str(self.root))
            Path(cmd[cmd.index('--output-last-message')+1]).write_text(reply)
            return subprocess.CompletedProcess(cmd, 0, 'unrelated log', '')
        with patch.object(server.shutil, 'which', return_value='/bin/codex'), patch.object(server.subprocess, 'run', side_effect=run):
            parsed, error = server.run_codex('prompt', self.root, None)
            self.assertEqual(parsed, json.loads(reply))
            self.assertEqual(error, '')
        with patch.object(server, 'run_claude', return_value=({'ideas':[]}, '')) as original:
            server.run_ai('prompt', self.root, None, client='claude')
            original.assert_called_once()

    def test_mindmap_stops_when_external_tools_cannot_be_inspected(self):
        server = module('plugins/mindmap-prompt/scripts/serve.py')
        with patch.object(server.shutil, 'which', return_value='/bin/codex'), patch.object(
                server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'private config')) as run:
            parsed, error = server.run_codex('prompt', self.root, None)
            self.assertIsNone(parsed)
            self.assertIn('expansion was not started', error)
            self.assertNotIn('private config', error)
            self.assertEqual(run.call_count, 1)

    def test_large_patch_checks_instruction_file_at_end(self):
        files = ''.join(f'*** Add File: src/f{i}.py\n+x=1\n' for i in range(250))
        files += ''.join(f'*** Add File: dir{i}/AGENTS.md\n+# Instructions\n' for i in range(500))
        result = self.hook('evolving-claude-md', 'skills/evolving-claude-md/lint-claude-md.py', inp={'command':
            '*** Begin Patch\n'+files+'*** Add File: AGENTS.md\n+- 2026-09-13 — bad\n*** End Patch'})
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_every_manifest_skill_path_exists(self):
        catalog=json.loads((ROOT/'.claude-plugin/marketplace.json').read_text())
        for entry in catalog['plugins']:
            plugin=ROOT/'plugins'/entry['name']
            manifest=json.loads((plugin/'.codex-plugin/plugin.json').read_text())
            self.assertTrue((plugin/manifest['skills']).is_dir(),entry['name'])
            self.assertTrue(list((plugin/manifest['skills']).glob('*/SKILL.md')),entry['name'])


if __name__ == '__main__':
    unittest.main()
