#!/usr/bin/env python3
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthesize_step import admits, parse_solution, step_equation, synthesize_trajectory

SOLUTION = """
solution: {
	d := { F }:tau
	c := { F }:tau
	r := { F }:tau
	a := { T }:tau
}
"""


class SynthesizeStepTests(unittest.TestCase):
    def test_parser_reads_the_witness_not_a_table(self):
        self.assertEqual(parse_solution(SOLUTION), {'a': 1, 'c': 0, 'r': 0, 'd': 0})
        self.assertIsNone(parse_solution('no solution\n'))

    def test_equation_uses_single_letter_names(self):
        equation = step_equation({'decided': False, 'pending': False, 'completed': False})
        self.assertNotIn('_', equation)
        self.assertIn('c = 0', equation)
        self.assertIn('r = 0', equation)
        self.assertIn('d = 0', equation)

    def test_call_is_not_forced_by_python_when_undecided(self):
        equation = step_equation({'decided': False, 'pending': False, 'completed': False})
        self.assertNotIn('c = 1', equation)
        self.assertTrue(callable(admits))


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class SynthesizeExecutionTests(unittest.TestCase):
    def test_tau_synthesizes_a_trajectory_and_rejects_a_contradiction(self):
        trace = synthesize_trajectory(bound=6)
        self.assertEqual(trace[0]['type'], 'session_start')
        self.assertEqual(trace[-1]['type'], 'session_end')
        self.assertIn('assistant', [event['type'] for event in trace])
        self.assertFalse(admits({'decided': False, 'pending': False, 'completed': False}, 'c'))


if __name__ == '__main__':
    unittest.main()
