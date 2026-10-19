#!/usr/bin/env python3
import shutil
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_step import gate, respond, step, stop_after_result


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


class AgentStepLawTests(unittest.TestCase):
    def test_the_host_does_not_contain_the_step_law(self):
        source = Path(__file__).resolve().parents[1].joinpath('scripts', 'agent_step.py').read_text()
        self.assertNotIn("c[0] = q[0]", source)
        self.assertNotIn('if named', source)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class AgentRespondTests(unittest.TestCase):
    def test_a_request_prints_one_tool_and_the_result_prints_stop(self):
        done = respond(1, 0)
        self.assertEqual(done['printed'], {'call': 1, 'tool_a': 1, 'tool_b': 0, 'stop': 0})
        self.assertEqual(done['ran'], 'a')
        self.assertEqual(done['next']['stop'], 1)
        self.assertEqual(done['next']['call'], 0)
        self.assertEqual(done['next']['tool_a'], 0)
        self.assertTrue(done['halted'])

    def test_the_other_name_prints_the_other_tool(self):
        done = respond(1, 1)
        self.assertEqual(done['ran'], 'b')
        self.assertEqual(done['printed']['tool_a'], 0)
        self.assertEqual(done['printed']['tool_b'], 1)
        self.assertTrue(done['halted'])

    def test_no_request_runs_nothing(self):
        done = respond(0, 1)
        self.assertIsNone(done['ran'])
        self.assertIsNone(done['result'])
        self.assertIsNone(done['next'])
        self.assertFalse(done['halted'])

    def test_a_result_prints_stop_and_no_tool(self):
        self.assertEqual(step(1, 1, 1), {'call': 0, 'tool_a': 0, 'tool_b': 0, 'stop': 1})

    def test_a_call_despite_a_result_is_unsat(self):
        self.assertIn('unsat', gate('gate_call_despite_result.tau'))

    def test_the_other_tool_is_unsat(self):
        self.assertIn('unsat', gate('gate_wrong_tool.tau'))
