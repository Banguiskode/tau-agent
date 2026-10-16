#!/usr/bin/env python3
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_tau_trace import emit_cases
from llm_harness import validate_trace
from trajectory_portfolio import load_portfolio, summarize_portfolio

ROOT = Path(__file__).resolve().parents[1]
ALLOW = {'tau_real_portfolio_gate'}


class TrajectoryPortfolioTests(unittest.TestCase):
    def test_decision_only_trace_still_has_a_negation(self):
        events = [
            {'type': 'session_start'},
            {'type': 'assistant'},
            {'type': 'session_end', 'status': 'PASS'},
        ]
        cases = emit_cases(events)
        self.assertEqual(cases['negate_fact']['conjuncts'][:-1], cases['kernel']['conjuncts'])
        self.assertEqual(cases['negate_fact']['conjuncts'][-1], 'assistant[2] = 0')
        self.assertIn('(done[3] = 1 -> assistant[2] = 1)', cases['kernel']['conjuncts'])

    def test_portfolio_covers_distinct_shapes_and_both_verdicts(self):
        rows = load_portfolio(ROOT / 'docs' / 'trajectory_portfolio.json')
        shapes = {tuple(event['type'] for event in row['events']) for row in rows}
        self.assertGreaterEqual(len(shapes), 3)
        self.assertGreaterEqual(len(shapes), len(rows) - 1)
        kernels = {row['kernel_expected'] for row in rows}
        self.assertEqual(kernels, {'SAT', 'UNSAT'})

    def test_harness_accepts_a_call_the_tau_policy_rejects(self):
        rows = load_portfolio(ROOT / 'docs' / 'trajectory_portfolio.json')
        illegal = next(row for row in rows if row['name'] == 'call_without_decision')
        report = validate_trace(illegal['events'], ALLOW)
        self.assertTrue(report['valid'])
        self.assertEqual(illegal['kernel_expected'], 'UNSAT')
        self.assertEqual(illegal['harness_expected'], 'PASS')

    def test_summary_fails_when_one_kernel_mismatches(self):
        ok = {'kernel_expected': 'SAT', 'kernel_obtained': 'SAT',
              'harness_expected': 'PASS', 'harness_obtained': 'PASS', 'shape': 'a'}
        bad = dict(ok, kernel_obtained='UNSAT', shape='b')
        only_sat = summarize_portfolio([ok, dict(ok, shape='c')])
        self.assertEqual(only_sat['status'], 'FAIL')
        mixed = summarize_portfolio([ok, bad, dict(ok, kernel_expected='UNSAT',
                                                    kernel_obtained='UNSAT', shape='c')])
        self.assertEqual(mixed['matched'], 2)
        self.assertEqual(mixed['status'], 'FAIL')

    def test_summary_passes_only_when_every_distinct_path_matches(self):
        rows = [
            {'kernel_expected': 'SAT', 'kernel_obtained': 'SAT',
             'harness_expected': 'PASS', 'harness_obtained': 'PASS', 'shape': 'a'},
            {'kernel_expected': 'SAT', 'kernel_obtained': 'SAT',
             'harness_expected': 'PASS', 'harness_obtained': 'PASS', 'shape': 'b'},
            {'kernel_expected': 'UNSAT', 'kernel_obtained': 'UNSAT',
             'harness_expected': 'PASS', 'harness_obtained': 'PASS', 'shape': 'c'},
        ]
        report = summarize_portfolio(rows)
        self.assertEqual(report['traces'], 3)
        self.assertEqual(report['shapes'], 3)
        self.assertEqual(report['status'], 'PASS')


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class TrajectoryPortfolioExecutionTests(unittest.TestCase):
    def test_portfolio_matches_executed_kernels(self):
        from trajectory_portfolio import run_portfolio
        report = run_portfolio(ROOT / 'docs' / 'trajectory_portfolio.json',
                               ROOT / 'trajectory_portfolio.json')
        self.assertEqual(report['status'], 'PASS', json.dumps(report['rows'], ensure_ascii=False))
        self.assertGreaterEqual(report['shapes'], 3)
        self.assertIn('UNSAT', {row['kernel_obtained'] for row in report['rows']})
        self.assertIn('SAT', {row['kernel_obtained'] for row in report['rows']})


if __name__ == '__main__':
    unittest.main()
