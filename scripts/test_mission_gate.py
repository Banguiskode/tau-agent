#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mission_gate import summarize_mission


class MissionGateTests(unittest.TestCase):
    def test_only_all_layers_pass_is_success(self):
        self.assertEqual(summarize_mission(True, True, True)['status'], 'PASS')

    def test_trace_failure_blocks_mission(self):
        report = summarize_mission(False, True, True)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['blocked_by'], 'trace')

    def test_replay_failure_blocks_mission(self):
        report = summarize_mission(True, False, True)
        self.assertEqual(report['blocked_by'], 'replay')

    def test_tau_failure_blocks_mission(self):
        report = summarize_mission(True, True, False)
        self.assertEqual(report['blocked_by'], 'tau')


if __name__ == '__main__':
    unittest.main()
