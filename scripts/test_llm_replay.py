#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_replay import replay_trace


class LLMReplayTests(unittest.TestCase):
    def test_replays_matching_tool_result(self):
        events = [
            {'type': 'tool_call', 'tool': 'tau_gate', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': True, 'summary': 'PASS'},
        ]
        report = replay_trace(events, {'c1': {'ok': True, 'summary': 'PASS'}})
        self.assertTrue(report['replayed'])
        self.assertEqual(report['checked_calls'], 1)

    def test_detects_nondeterministic_result(self):
        events = [
            {'type': 'tool_call', 'tool': 'tau_gate', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': False, 'summary': 'FAIL'},
        ]
        report = replay_trace(events, {'c1': {'ok': True, 'summary': 'PASS'}})
        self.assertFalse(report['replayed'])
        self.assertIn('result mismatch', report['errors'][0])

    def test_detects_missing_fixture(self):
        report = replay_trace([{'type': 'tool_call', 'call_id': 'c1'}], {})
        self.assertFalse(report['replayed'])
        self.assertIn('missing fixture', report['errors'][0])


if __name__ == '__main__':
    unittest.main()
