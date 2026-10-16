#!/usr/bin/env python3
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_rule import complement_script, parse_written_rule, reinstall_script

FIXTURE = """
Execution step: 0
i1[0] : tau := o2[t] = 1.
o1[0] := sometimes o2[t]:tau' != 0
"""


class WriteRuleTests(unittest.TestCase):
    def test_the_source_states_the_fact_not_the_rule(self):
        script = complement_script('o2[t] = 1.')
        self.assertIn('o2[t] = 1.', script)
        self.assertNotIn('sometimes', script)
        self.assertEqual(parse_written_rule(FIXTURE), "sometimes o2[t]:tau' != 0")
        self.assertIsNone(parse_written_rule('Failed to parse input value\n'))
        self.assertNotIn(':tau', reinstall_script("sometimes o2[t]:tau' != 0"))
        self.assertIn("sometimes o2[t]' != 0.", reinstall_script("sometimes o2[t]:tau' != 0"))


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class WriteRuleExecutionTests(unittest.TestCase):
    def test_tau_writes_the_dual_and_a_bad_name_writes_nothing(self):
        from write_rule import write_rule
        root = Path(__file__).resolve().parents[1]
        written = write_rule(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertIn('sometimes', written['rule'])
        self.assertIn('o2', written['rule'])
        self.assertNotIn('sometimes', written['script'])
        self.assertIsNone(write_rule(root / 'docs' / 'trajectories' / 'single_call.jsonl'))
        self.assertIsNone(write_rule(root / 'docs' / 'trajectories' / 'local_session.jsonl', fact='a[3] = 1.'))
        from write_rule import reinstall
        installed = reinstall(written['rule'])
        self.assertIn('sbf', installed['updated'])
        self.assertIn(3, installed['off'])
        self.assertIsNone(reinstall(None))
        from write_rule import replace_event, replacement_equation
        events = [json.loads(line) for line in (root / 'docs' / 'trajectories' / 'local_session.jsonl').read_text().splitlines() if line.strip()]
        equation = replacement_equation(events, 3)
        clauses = set(equation.split(' && '))
        self.assertIn('a3 = 0', clauses)
        self.assertNotIn('s3 = 1', clauses)
        self.assertNotIn('d3 = 1', clauses)
        replaced = replace_event(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(replaced['point'], 3)
        self.assertNotEqual(replaced['replacement'], 'assistant')
        self.assertTrue(replaced['decision_still_possible'])
        self.assertIsNone(replace_event(root / 'docs' / 'trajectories' / 'single_call.jsonl'))
        from write_rule import legal_replacements
        legal = legal_replacements(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(legal['point'], 3)
        self.assertEqual(
            set(legal['legal']),
            {'tool_call', 'tool_result', 'session_end'},
        )
        self.assertNotIn('assistant', legal['legal'])
        from write_rule import impose, mission_equation
        equation = mission_equation(events, 3, 'end')
        clauses = set(equation.split(' && '))
        self.assertIn('c3 = 0', clauses)
        self.assertIn('s3 = 0', clauses)
        self.assertNotIn('d3 = 1', clauses)
        imposed = impose(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(imposed['chosen']['end'], 'session_end')
        self.assertEqual(imposed['chosen']['call'], 'tool_call')
        self.assertEqual(imposed['chosen']['result'], 'tool_result')
        self.assertIsNone(imposed['chosen']['none'])
        from write_rule import draw_mission, drawn_equation
        equation = drawn_equation(events, 3, 'session_end')
        clauses = set(equation.split(' && '))
        self.assertIn('d3 = 1', clauses)
        self.assertNotIn('x0 = 1', clauses)
        self.assertNotIn('x1 = 1', clauses)
        self.assertNotIn('x2 = 1', clauses)
        session = draw_mission(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(session['kept'], ['session_end'])
        self.assertEqual(set(session['banned']), {'tool_call', 'tool_result'})
        two = draw_mission(root / 'docs' / 'trajectories' / 'local_two_calls.jsonl')
        self.assertEqual(two['kept'], ['tool_call'])
        self.assertEqual(set(two['banned']), {'tool_result', 'session_end'})
        from write_rule import decide_keep, keep_equation
        equation = keep_equation(events, 3, 'session_end')
        clauses = set(equation.split(' && '))
        self.assertNotIn('m = 0', clauses)
        self.assertNotIn('m = 1', clauses)
        decided = decide_keep(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(decided['free'], 'discard')
        self.assertTrue(decided['keep_possible'])
        self.assertTrue(decided['discard_possible'])
        self.assertFalse(decided['keep_decision'])
        from write_rule import reasoned_keep, reason_equation
        equation = reason_equation(events, 3, 'session_end')
        clauses = set(equation.split(' && '))
        self.assertIn("d3' & s2 = 0", clauses)
        self.assertNotIn('m = 0', clauses)
        self.assertNotIn('m = 1', clauses)
        self.assertNotIn('d3 = 1', clauses)
        session = reasoned_keep(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(session['free'], 'keep')
        self.assertEqual(session['free_event'], 'session_end')
        self.assertFalse(session['discard_possible'])
        two = reasoned_keep(root / 'docs' / 'trajectories' / 'local_two_calls.jsonl')
        self.assertEqual(two['free'], 'discard')
        self.assertEqual(two['free_event'], 'session_end')
        self.assertFalse(two['keep_possible'])


if __name__ == '__main__':
    unittest.main()
