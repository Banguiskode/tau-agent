#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_agents import summarize_comparison


class CompareAgentsTests(unittest.TestCase):
    def test_all_agents_pass(self):
        self.assertEqual(summarize_comparison([
            {'agent': 'hermes', 'status': 'PASS'},
            {'agent': 'claude_code', 'status': 'PASS'},
        ]), {'agents': 2, 'pass': 2, 'fail': 0, 'all_pass': True})

    def test_one_failure_is_visible(self):
        self.assertEqual(summarize_comparison([
            {'agent': 'hermes', 'status': 'PASS'},
            {'agent': 'claude_code', 'status': 'FAIL'},
        ]), {'agents': 2, 'pass': 1, 'fail': 1, 'all_pass': False})

    def test_empty_comparison_is_not_pass(self):
        self.assertFalse(summarize_comparison([])['all_pass'])


if __name__ == '__main__':
    unittest.main()
