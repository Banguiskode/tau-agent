#!/usr/bin/env python3
import shutil
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_step import gate, perform, respond, step, stop_after_result, trace_of
from llm_harness import validate_trace


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


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class AgentLiveTests(unittest.TestCase):
    def test_the_host_does_not_contain_the_live_law(self):
        source = Path(__file__).resolve().parents[1].joinpath('scripts', 'agent_step.py').read_text()
        self.assertNotIn('s[1] = i[1]', source)
        self.assertNotIn('isfile', source)
        self.assertNotIn('getsize', source)
        self.assertNotIn('e[0] & z[0]', source)
        self.assertNotIn('a[1] = c[1]', source)

    def test_a_nonempty_file_prints_stop_after_the_call(self):
        folder = Path(self._worlds('pas un bit', missing_b=True))
        done = perform(1, 0, folder / 'a', folder / 'b')
        self.assertEqual(done['printed'], {'call': 1, 'tool_a': 1, 'tool_b': 0, 'stop': 0})
        self.assertEqual(done['ran'], 'a')
        self.assertEqual(done['result'], 1)
        self.assertEqual(done['next']['stop'], 1)
        self.assertEqual(done['next']['call'], 0)
        self.assertIsNone(done['followed'])
        self.assertIsNone(done['after'])
        self.assertTrue(done['halted'])
        trace = trace_of(done)
        report = validate_trace(trace, {'file_nonempty', 'path_is_dir'})
        self.assertTrue(report['valid'])
        self.assertEqual(trace[1]['type'], 'assistant')
        self.assertEqual(trace[2]['tool'], 'file_nonempty')
        self.assertTrue(trace[3]['ok'])
        self.assertEqual(trace[-1]['type'], 'session_end')
        import json
        import tempfile
        from run_tau_gate import run_emitted
        folder = Path(tempfile.mkdtemp())
        trace_path = folder / 'trace.jsonl'
        trace_path.write_text(''.join(json.dumps(event) + '\n' for event in trace))
        verdict = run_emitted(trace_path, 20)
        self.assertEqual(verdict['status'], 'PASS')
        self.assertTrue(all(case['obtained'] == case['expected'] for case in verdict['cases']))
        self.assertNotIn("g[0] = q[0]", Path(__file__).resolve().parents[1].joinpath('scripts', 'agent_step.py').read_text())

    def test_a_missing_file_does_not_print_stop(self):
        missing = Path('/tmp/tau-agent-missing-tool-a')
        done = perform(1, 0, missing, missing)
        self.assertEqual(done['ran'], 'a')
        self.assertEqual(done['result'], 0)
        self.assertEqual(done['next']['call'], 1)
        self.assertEqual(done['next']['tool_b'], 1)
        self.assertEqual(done['next']['stop'], 0)
        self.assertEqual(done['followed'], 'b')
        self.assertEqual(done['followed_result'], 0)
        self.assertEqual(done['after']['stop'], 0)
        self.assertEqual(done['after']['call'], 0)
        self.assertFalse(done['halted'])
        import json
        import tempfile
        from run_tau_gate import run_emitted
        trace = trace_of(done)
        trace_path = Path(tempfile.mkdtemp()) / 'trace.jsonl'
        trace_path.write_text(''.join(json.dumps(event) + '\n' for event in trace))
        verdict = run_emitted(trace_path, 20)
        self.assertEqual(verdict['status'], 'NO_END')
        self.assertEqual(verdict['cases'], [])

    def test_the_other_tool_is_not_run(self):
        folder = Path(self._worlds('1', which='b'))
        done = perform(1, 1, folder / 'missing', folder)
        self.assertEqual(done['ran'], 'b')
        self.assertEqual(done['result'], 1)
        self.assertIsNone(done['followed'])
        self.assertIsNone(done['after'])
        self.assertTrue(done['halted'])

    def test_no_request_runs_no_tool(self):
        missing = Path('/tmp/tau-agent-missing-world')
        done = perform(0, 1, missing, missing)
        self.assertIsNone(done['ran'])
        self.assertIsNone(done['result'])
        self.assertEqual(done['printed']['call'], 0)
        self.assertFalse(done['halted'])

    def test_an_empty_file_does_not_print_stop(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        (folder / 'a').write_text('')
        done = perform(1, 0, folder / 'a', folder / 'missing')
        self.assertEqual(done['ran'], 'a')
        self.assertEqual(done['result'], 0)
        self.assertEqual(done['followed'], 'b')
        self.assertEqual(done['followed_result'], 0)
        self.assertEqual(done['after']['call'], 0)
        self.assertEqual(done['after']['stop'], 0)
        self.assertFalse(done['halted'])
        trace = trace_of(done)
        self.assertEqual([event['type'] for event in trace], [
            'session_start', 'assistant', 'tool_call', 'tool_result', 'tool_call', 'tool_result',
        ])
        self.assertEqual(trace[4]['tool'], 'path_is_dir')
        self.assertFalse(trace[3]['ok'])
        self.assertFalse(validate_trace(trace, {'file_nonempty', 'path_is_dir'})['valid'])

    def test_the_other_tool_returning_one_prints_stop(self):
        import json
        import tempfile
        from run_tau_gate import run_emitted
        folder = Path(tempfile.mkdtemp())
        (folder / 'a').write_text('')
        done = perform(1, 0, folder / 'a', folder)
        self.assertEqual(done['followed'], 'b')
        self.assertEqual(done['followed_result'], 1)
        self.assertEqual(done['after']['stop'], 1)
        self.assertEqual(done['after']['call'], 0)
        self.assertTrue(done['halted'])
        trace = trace_of(done)
        self.assertEqual(trace[-1]['type'], 'session_end')
        trace_path = folder / 'trace.jsonl'
        trace_path.write_text(''.join(json.dumps(event) + '\n' for event in trace))
        verdict = run_emitted(trace_path, 20)
        self.assertEqual(verdict['status'], 'PASS')

    def test_a_forced_bit_against_a_missing_file_is_unsat(self):
        self.assertIn('unsat', gate('tools/gate_nonempty.tau'))

    def _worlds(self, bit: str, missing_b: bool = False, which: str = 'a') -> str:
        import tempfile
        folder = tempfile.mkdtemp()
        target = Path(folder) / which
        target.write_text(bit + '\n')
        if not missing_b and which != 'b':
            (Path(folder) / 'b').write_text('1\n')
        return folder
