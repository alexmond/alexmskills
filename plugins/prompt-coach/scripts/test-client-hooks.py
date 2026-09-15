#!/usr/bin/env python3
"""Client contract tests with isolated state and synthetic transcripts."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('coach_clients', HERE / 'analyze-prompt.py')
coach = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = coach
spec.loader.exec_module(coach)


class ClientHooks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.transcript = self.root / 'session.jsonl'
        coach.GLOBAL_DIR = self.root / 'global'
        coach.GLOBAL_STATE = coach.GLOBAL_DIR / 'state.json'
        coach.GLOBAL_CONFIG = coach.GLOBAL_DIR / 'config.json'
        coach._CLAUDE_PROJECTS_DIR = self.root / 'claude-projects'
        coach._HOOK_PAYLOAD = {}

    def write_transcript(self, *entries):
        self.transcript.write_text('\n'.join(json.dumps(e) for e in entries))

    def submit(self, prompt, **extra):
        payload = {'prompt': prompt, 'cwd': str(self.repo),
                   'hook_event_name': 'UserPromptSubmit', **extra}
        output = io.StringIO()
        with patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output):
            self.assertEqual(coach.main(), 0)
        return json.loads(output.getvalue()) if output.getvalue().strip() else {}

    def test_both_clients_emit_and_share_existing_state(self):
        for extra in ({'session_id': 'claude'}, {'session_id': 'codex', 'turn_id': 'turn',
                      'transcript_path': None, 'model': 'test-model'}):
            result = self.submit('Fix the bug in the login page.', **extra)
            hook = result['hookSpecificOutput']
            self.assertEqual(hook['hookEventName'], 'UserPromptSubmit')
            self.assertTrue(hook['additionalContext'])
        self.assertEqual(json.loads(coach.GLOBAL_STATE.read_text())['prompt_count'], 2)
        self.assertTrue((self.repo / '.claude/prompt-coach/log.md').exists())

    def test_clarification_answers_skip_coaching_in_both_formats(self):
        entries = [
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'AskUserQuestion'}]}},
            {'type': 'response_item', 'payload': {'type': 'function_call',
                'name': 'functions.request_user_input', 'arguments': '{}'}},
            {'type': 'response_item', 'payload': {'type': 'function_call',
                'name': 'request_user_input_async', 'arguments': '{}'}},
        ]
        for entry in entries:
            with self.subTest(entry=entry):
                self.write_transcript(entry)
                result = self.submit('Use the existing login page implementation.',
                                     transcript_path=str(self.transcript))
                self.assertEqual(result, {})
                self.assertIn('skipped:multi-choice-answer',
                              (self.repo / '.claude/prompt-coach/log.md').read_text())

    def test_codex_assistant_text_and_timestamp(self):
        for record_type, payload in (
            ('response_item', {'type': 'message', 'role': 'assistant', 'content': [
                {'type': 'output_text', 'text': 'Choose one?\n- First option\n- Second option'}]}),
            ('event_msg', {'type': 'agent_message', 'message':
                'Choose one?\n- First option\n- Second option'}),
        ):
            self.write_transcript({'type': record_type, 'timestamp': '2026-09-12T12:00:00Z',
                                   'payload': payload})
            coach._HOOK_PAYLOAD = {'transcript_path': str(self.transcript)}
            entry = coach._last_assistant_turn(self.repo)
            self.assertEqual(entry['timestamp'], '2026-09-12T12:00:00Z')
            self.assertIn('Choose one?', coach._assistant_text(entry))
            self.assertEqual(coach.picker_answer_reason(self.repo), 'option-list-answer')

    def test_explicit_missing_transcript_never_borrows_claude_session(self):
        legacy = coach._CLAUDE_PROJECTS_DIR / str(self.repo).replace('/', '-')
        legacy.mkdir(parents=True)
        (legacy / 'other.jsonl').write_text(json.dumps({'type': 'assistant',
            'message': {'content': [{'type': 'tool_use', 'name': 'AskUserQuestion'}]}}))
        for payload in ({'transcript_path': None}, {'transcript_path': str(self.transcript)},
                        {'turn_id': 'codex'}, {'session_id': 'missing'}):
            coach._HOOK_PAYLOAD = payload
            self.assertIsNone(coach._last_assistant_turn(self.repo))
        coach._HOOK_PAYLOAD = {}  # legacy callers still have a fallback
        self.assertIsNotNone(coach._last_assistant_turn(self.repo))

    def test_latest_activity_supersedes_old_picker(self):
        self.write_transcript(
            {'type': 'response_item', 'payload': {'type': 'function_call',
                'name': 'request_user_input'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant',
                'content': [{'type': 'output_text', 'text': 'Implementation is complete.'}]}},
            {'type': 'unknown'},
        )
        coach._HOOK_PAYLOAD = {'transcript_path': str(self.transcript)}
        self.assertIsNone(coach.picker_answer_reason(self.repo))

    def test_conversational_reply_and_malformed_records(self):
        self.transcript.write_text('not json\nnull\n[]\n{"type":"unknown"}\n')
        self.assertEqual(self.submit('yes', turn_id='t', transcript_path=str(self.transcript)), {})
        self.assertIsNone(coach._last_assistant_turn(self.repo))

    def test_codex_manifest_enables_reviewed_hook(self):
        manifest = json.loads((HERE.parent / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['hooks'], './hooks/codex.json')
        hooks = json.loads((HERE.parent / manifest['hooks']).read_text())
        handler = hooks['hooks']['UserPromptSubmit'][0]['hooks'][0]
        self.assertIn('${PLUGIN_ROOT}', handler['command'])
        self.assertGreater(handler['additionalContextLimit'], 3891)


if __name__ == '__main__':
    unittest.main()
