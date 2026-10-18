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
        from write_rule import choose_law, law_equation
        from synthesize_step import solve_assignments
        equation = law_equation(events, 3, 'session_end')
        clauses = set(equation.split(' && '))
        self.assertNotIn('n0 = 1', clauses)
        self.assertNotIn('n1 = 1', clauses)
        self.assertNotIn('m = 0', clauses)
        self.assertNotIn('m = 1', clauses)
        self.assertNotIn('d3 = 1', clauses)
        self.assertIn('n0 | n1 = 1', clauses)
        session = choose_law(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(session['law'], 'stop_after_result')
        self.assertEqual(session['legal'], ['stop_after_result'])
        self.assertEqual(session['free'], 'keep')
        two = choose_law(root / 'docs' / 'trajectories' / 'local_two_calls.jsonl')
        self.assertEqual(two['law'], 'no_second_call')
        self.assertEqual(two['legal'], ['stop_after_result', 'no_second_call'])
        self.assertEqual(two['free'], 'discard')
        self.assertIsNone(choose_law(root / 'docs' / 'trajectories' / 'single_call.jsonl'))
        neither = [
            {'type': 'session_start'},
            {'type': 'assistant'},
            {'type': 'assistant'},
            {'type': 'session_end'},
        ]
        self.assertIsNone(solve_assignments(law_equation(neither, 1, 'session_end')))
        from write_rule import apply_written_reason, violation_fact, complement_script
        self.assertIsNone(violation_fact(neither))
        self.assertIsNone(apply_written_reason(root / 'docs' / 'trajectories' / 'single_call.jsonl'))
        written = apply_written_reason(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        source = complement_script(written['fact'])
        self.assertNotIn('sometimes', source)
        self.assertNotIn(written['rule'], source)
        self.assertIn('sometimes', written['rule'])
        self.assertEqual(written['free'], 'keep')
        self.assertEqual(written['free_event'], 'session_end')
        self.assertFalse(written['discard_possible'])
        two = apply_written_reason(root / 'docs' / 'trajectories' / 'local_two_calls.jsonl')
        self.assertEqual(two['rule'], written['rule'])
        self.assertEqual(two['free'], 'discard')
        self.assertEqual(two['free_event'], 'session_end')
        self.assertFalse(two['keep_possible'])
        from write_rule import name_violation, violation_equation
        equation = violation_equation(events)
        clauses = set(equation.split(' && '))
        self.assertNotIn('v0 = 1', clauses)
        self.assertNotIn('v1 = 1', clauses)
        self.assertNotIn('p3 = 1', clauses)
        self.assertIn('v0 | v1 = 1', clauses)
        named = name_violation(root / 'docs' / 'trajectories' / 'local_session.jsonl')
        self.assertEqual(named['kind'], 'result_then_not_end')
        self.assertEqual(named['point'], 3)
        self.assertEqual(named['legal'], [{'kind': 'result_then_not_end', 'point': 3}])
        self.assertNotIn('always', named['observed'])
        self.assertEqual(named['observed'], 'o2[t] = 1 && o3[t] = 1')
        self.assertNotIn('o5[t] = 0', named['observed'])
        self.assertIn('always', named['fact'])
        self.assertNotEqual(named['fact'], named['observed'])
        self.assertNotIn('sometimes', complement_script(named['fact']))
        self.assertEqual(named['free'], 'discard')
        self.assertFalse(named['keep_possible'])
        self.assertEqual(named['model'], 'tool_result')
        self.assertEqual(named['reason'], "d3' & s2 = 0")
        self.assertEqual(named['elected'], "d3' = 0")
        self.assertEqual(named['elected_value'], 1)
        self.assertEqual(named['event'], 'session_end')
        self.assertNotEqual(named['event'], named['model'])
        self.assertEqual(named['revised'][-1], {'type': 'session_end'})
        self.assertNotIn('status', named['revised'][-1])
        self.assertTrue(named['closed'])
        self.assertIsNone(named['empty_forced'])
        self.assertEqual(named['pinned'], 'o3')
        self.assertIn('o2[1]', named['still_unbound'])
        self.assertIn('o2[2]', named['later_off'])
        self.assertEqual(named['point_clause'], "o2[3]' != 0")
        self.assertNotIn('sometimes', named['point_clause'])
        self.assertEqual(named['point_fixed'], 0)
        self.assertEqual(named['legal_events'], ['tool_call', 'tool_result', 'session_end'])
        self.assertEqual(named['printed_off'], "a3' != 0")
        self.assertFalse(named['replacement_named'])
        self.assertIn('o2[1]', named['unbound'])
        self.assertFalse(named['replacement_executed'])
        from write_rule import named_apply_equation
        apply_eq = named_apply_equation(events, 3, named['clause'])
        self.assertNotIn(named['printed_off'], set(apply_eq.split(' && ')))
        self.assertNotIn(named['elected'], set(apply_eq.split(' && ')))
        named_two = name_violation(root / 'docs' / 'trajectories' / 'local_two_calls.jsonl')
        self.assertEqual(named_two['kind'], 'second_call')
        self.assertEqual(named_two['point'], 4)
        self.assertEqual(named_two['observed'], 'o4[t] = 1 && o2[t] = 1')
        self.assertEqual(named_two['legal'], [
            {'kind': 'result_then_not_end', 'point': 3},
            {'kind': 'second_call', 'point': 4},
        ])
        self.assertEqual(named_two['free'], 'discard')
        self.assertFalse(named_two['keep_possible'])
        self.assertEqual(named_two['legal_events'], ['assistant', 'tool_result', 'session_end'])
        self.assertEqual(named_two['printed_off'], "c4' != 0")
        self.assertFalse(named_two['replacement_named'])
        self.assertEqual(named_two['pinned'], 'o2')
        self.assertIn('o4[1]', named_two['still_unbound'])
        self.assertIn('o4[2]', named_two['later_off'])
        self.assertEqual(named_two['point_clause'], "o4[4]' != 0")
        self.assertEqual(named_two['point_fixed'], 0)
        self.assertIsNone(named_two['event'])
        self.assertIsNone(named_two['reason'])
        self.assertIsNone(named_two['elected'])
        self.assertIsNone(named_two['revised'])
        self.assertFalse(named_two['empty_forced'])
        self.assertTrue(named_two['empty_possible'])
        self.assertIsNone(named_two['closed'])
        self.assertEqual(named_two['run_model'], 'session_end')
        self.assertEqual(named_two['run_legal'], ['assistant', 'tool_result', 'session_end'])
        self.assertNotEqual(named_two['run_model'], named_two['model'])
        self.assertFalse(named_two['replacement_executed'])
        self.assertIsNone(name_violation(root / 'docs' / 'trajectories' / 'single_call.jsonl'))


if __name__ == '__main__':
    unittest.main()
