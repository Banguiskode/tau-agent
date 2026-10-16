#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_mutations import mutate_trace


class LLMMutationTests(unittest.TestCase):
    def setUp(self):
        self.trace = [
            {'type': 'session_start'},
            {'type': 'assistant'},
            {'type': 'tool_call', 'tool': 'tau_gate', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': True},
            {'type': 'session_end', 'status': 'PASS'},
        ]

    def test_disallowed_tool_mutation_changes_tool(self):
        mutated = mutate_trace(self.trace, 'disallowed_tool')
        self.assertEqual(mutated[2]['tool'], 'forbidden_tool')

    def test_orphan_result_removes_call(self):
        mutated = mutate_trace(self.trace, 'orphan_result')
        self.assertFalse(any(e.get('type') == 'tool_call' for e in mutated))
        self.assertTrue(any(e.get('type') == 'tool_result' for e in mutated))

    def test_early_stop_removes_terminal_event(self):
        mutated = mutate_trace(self.trace, 'early_stop')
        self.assertFalse(any(e.get('type') == 'session_end' for e in mutated))

    def test_unknown_mutation_rejected(self):
        with self.assertRaises(ValueError):
            mutate_trace(self.trace, 'unknown')


if __name__ == '__main__':
    unittest.main()
