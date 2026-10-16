#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_tau_trace import emit_cases, render_spec
from mission_gate import tau_gate_command
from compare_agents import tau_gate_command as compare_tau_command

ROOT = Path(__file__).resolve().parents[1]
HERMES = [
    {'type': 'session_start'},
    {'type': 'assistant'},
    {'type': 'tool_call', 'call_id': 'h1', 'tool': 'tau_real_portfolio_gate'},
    {'type': 'tool_result', 'call_id': 'h1', 'ok': True},
    {'type': 'assistant'},
    {'type': 'session_end', 'status': 'PASS'},
]


class EmitTauTraceTests(unittest.TestCase):
    def test_canonical_trace_pins_facts_and_indexed_links(self):
        cases = emit_cases(HERMES)
        kernel = cases['kernel']['conjuncts']
        self.assertIn('([t < 1] -> assistant[t] = 0)', kernel)
        self.assertIn('assistant[2] = 1', kernel)
        self.assertIn('tool_call[3] = 1', kernel)
        self.assertIn('tool_result[4] = 1', kernel)
        self.assertIn('done[6] = 1', kernel)
        self.assertIn('(tool_call[3] = 1 -> assistant[2] = 1)', kernel)
        self.assertIn('(tool_result[4] = 1 -> tool_call[3] = 1)', kernel)
        self.assertIn('(done[6] = 1 -> tool_result[4] = 1)', kernel)
        self.assertNotIn('[t-1]', ' '.join(kernel))
        self.assertNotIn('[t >=', ' '.join(kernel))
        spec = render_spec(kernel)
        self.assertEqual(sum(line.startswith('r ') for line in spec.splitlines()), 1)

    def test_result_links_to_matching_call_not_the_nearest(self):
        events = [
            {'type': 'session_start'},
            {'type': 'assistant'},
            {'type': 'tool_call', 'call_id': 'a'},
            {'type': 'tool_call', 'call_id': 'b'},
            {'type': 'tool_result', 'call_id': 'b'},
            {'type': 'tool_result', 'call_id': 'a'},
            {'type': 'session_end'},
        ]
        kernel = emit_cases(events)['kernel']['conjuncts']
        self.assertIn('(tool_result[5] = 1 -> tool_call[4] = 1)', kernel)
        self.assertIn('(tool_result[6] = 1 -> tool_call[3] = 1)', kernel)
        self.assertNotIn('(tool_result[6] = 1 -> tool_call[4] = 1)', kernel)

    def test_mutation_adds_a_negation_to_the_intact_kernel(self):
        cases = emit_cases(HERMES)
        kernel = cases['kernel']['conjuncts']
        mutation = cases['negate_fact']['conjuncts']
        self.assertEqual(mutation[:-1], kernel)
        self.assertEqual(mutation[-1], 'tool_result[4] = 0')
        self.assertEqual(cases['negate_fact']['expected'], 'UNSAT')
        self.assertEqual(cases['kernel']['expected'], 'SAT')

    def test_link_probe_omits_the_consequent_fact(self):
        cases = emit_cases(HERMES)
        probe = cases['link_probe']['conjuncts']
        self.assertIn('(done[6] = 1 -> tool_result[4] = 1)', probe)
        self.assertIn('done[6] = 1', probe)
        self.assertNotIn('tool_result[4] = 1', probe)
        self.assertEqual(cases['link_probe_neg']['conjuncts'], probe + ['tool_result[4] = 0'])
        self.assertEqual(cases['link_probe']['expected'], 'SAT')
        self.assertEqual(cases['link_probe_neg']['expected'], 'UNSAT')

    def test_control_assigns_a_time_the_kernel_does_not_pin(self):
        cases = emit_cases(HERMES)
        self.assertEqual(cases['control_free']['conjuncts'][-1], 'assistant[7] = 1')
        self.assertNotIn('assistant[7] = 1', cases['kernel']['conjuncts'])
        self.assertEqual(cases['control_free']['expected'], 'SAT')

    def test_missing_predecessor_is_encoded_at_zero_not_invented(self):
        events = [
            {'type': 'session_start'},
            {'type': 'tool_call', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1'},
            {'type': 'session_end'},
        ]
        kernel = emit_cases(events)['kernel']['conjuncts']
        self.assertIn('(tool_call[2] = 1 -> assistant[0] = 1)', kernel)
        self.assertIn('assistant[1] = 0', kernel)

    def test_mission_gate_points_tau_at_the_trace(self):
        command = tau_gate_command(Path('docs/hermes_trace_canonical.jsonl'))
        self.assertIn('--trace', command)
        self.assertIn('docs/hermes_trace_canonical.jsonl', command)
        self.assertNotIn('agent_transition.tau', ' '.join(command))

    def test_comparison_uses_each_agents_own_trace(self):
        hermes = compare_tau_command(Path('docs/hermes_trace_canonical.jsonl'), Path('tau/hermes.json'))
        claude = compare_tau_command(Path('docs/claude_trace_canonical.jsonl'), Path('tau/claude.json'))
        self.assertIn('docs/hermes_trace_canonical.jsonl', hermes)
        self.assertIn('docs/claude_trace_canonical.jsonl', claude)
        self.assertNotEqual(hermes, claude)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class EmitTauExecutionTests(unittest.TestCase):
    def test_canonical_trace_matches_expected_verdicts(self):
        output = Path('/tmp/tau_agent_trace_verdict.json')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'run_tau_gate.py'),
             '--trace', str(ROOT / 'docs' / 'hermes_trace_canonical.jsonl'),
             '--output', str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['source'], 'trace')

    def test_call_without_prior_decision_is_unsat(self):
        trace = Path('/tmp/tau_agent_policy_break.jsonl')
        trace.write_text('\n'.join(json.dumps(event) for event in [
            {'type': 'session_start'},
            {'type': 'tool_call', 'call_id': 'c1', 'tool': 'tau_real_portfolio_gate'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': True},
            {'type': 'session_end', 'status': 'PASS'},
        ]) + '\n')
        output = Path('/tmp/tau_agent_policy_break.json')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'run_tau_gate.py'),
             '--trace', str(trace), '--output', str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(output.read_text())
        kernel = next(case for case in report['cases'] if case['case'] == 'kernel')
        self.assertEqual(kernel['obtained'], 'UNSAT')


if __name__ == '__main__':
    unittest.main()
