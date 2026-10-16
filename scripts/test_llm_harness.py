#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_harness import validate_trace


class LLMHarnessTests(unittest.TestCase):
    def test_valid_model_tool_cycle(self):
        trace = [
            {'type': 'session_start'},
            {'type': 'assistant', 'content': 'run check'},
            {'type': 'tool_call', 'tool': 'tau_gate', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': True},
            {'type': 'assistant', 'content': 'verified'},
            {'type': 'session_end', 'status': 'PASS'},
        ]
        report = validate_trace(trace, {'tau_gate'})
        self.assertTrue(report['valid'])
        self.assertEqual(report['tool_calls'], 1)

    def test_rejects_unpaired_tool_result(self):
        report = validate_trace([{'type': 'session_start'},
                                 {'type': 'tool_result', 'call_id': 'missing'},
                                 {'type': 'session_end'}], {'tau_gate'})
        self.assertFalse(report['valid'])
        self.assertIn('orphan tool_result', report['errors'][0])

    def test_rejects_disallowed_tool(self):
        report = validate_trace([{'type': 'session_start'},
                                 {'type': 'assistant'},
                                 {'type': 'tool_call', 'tool': 'shell', 'call_id': 'c1'}],
                                {'tau_gate'})
        self.assertFalse(report['valid'])
        self.assertIn('disallowed tool', report['errors'][0])

    def test_rejects_trace_without_terminal_event(self):
        report = validate_trace([{'type': 'session_start'}, {'type': 'assistant'}], set())
        self.assertFalse(report['valid'])
        self.assertIn('terminal', report['errors'][0])


if __name__ == '__main__':
    unittest.main()
