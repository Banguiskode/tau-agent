#!/usr/bin/env python3
import shutil
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_step import gate, stop_after_result


class AgentHostTests(unittest.TestCase):
    def test_the_host_does_not_contain_the_law(self):
        source = Path(__file__).resolve().parents[1].joinpath('scripts', 'agent_step.py').read_text()
        self.assertNotIn('s[t] = i[t-1]', source)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class AgentStepTests(unittest.TestCase):
    def test_stop_is_printed_the_step_after_a_result(self):
        self.assertEqual(stop_after_result([0, 0, 1, 0]), [0, 0, 0, 1])

    def test_a_call_the_step_after_a_result_is_unsat(self):
        self.assertIn('unsat', gate('gate_call_after_result.tau'))

    def test_the_stop_gate_prints_the_named_bits(self):
        text = gate('gate_stop_after_result.tau')
        self.assertNotIn('unsat', text)
        self.assertIn('s[3] := 1', text)
        self.assertIn('c[3] := 0', text)
        self.assertIn('i[2] := 1', text)
