#!/usr/bin/env python3
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revise_session import session_equation

TRACE = Path(__file__).resolve().parents[1] / 'docs' / 'trajectories' / 'local_session.jsonl'


class ReviseSessionTests(unittest.TestCase):
    def test_the_revision_does_not_copy_the_recorded_continuation(self):
        events = [json.loads(line) for line in TRACE.read_text().splitlines() if line.strip()]
        body = [event for event in events if event['type'] != 'session_start']
        result_at = next(index for index, event in enumerate(body) if event['type'] == 'tool_result')
        self.assertEqual(body[result_at + 1]['type'], 'assistant')
        clauses = set(session_equation(events).split(' && '))
        self.assertIn('c1 = 1', clauses)
        self.assertIn('s2 = 1', clauses)
        self.assertIn("d3' & s2 = 0", clauses)
        self.assertNotIn('d3 = 1', clauses)
        self.assertNotIn('a3 = 1', clauses)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class ReviseSessionExecutionTests(unittest.TestCase):
    def test_tau_keeps_the_prefix_and_ends_instead_of_deciding_again(self):
        from revise_session import revise_session
        trace = revise_session(TRACE)
        self.assertEqual(
            [event['type'] for event in trace],
            ['session_start', 'assistant', 'tool_call', 'tool_result', 'session_end'],
        )
        self.assertIsNone(revise_session(TRACE, deny_call=True))


TWO = Path(__file__).resolve().parents[1] / 'docs' / 'trajectories' / 'local_two_calls.jsonl'


class ChainTests(unittest.TestCase):
    def test_two_links_do_not_pin_the_filled_steps(self):
        from revise_session import chain_equation
        events = [json.loads(line) for line in TWO.read_text().splitlines() if line.strip()]
        body = [event for event in events if event['type'] != 'session_start']
        self.assertEqual(body[3]['type'], 'assistant')
        self.assertEqual(body[4]['type'], 'tool_call')
        clauses = set(chain_equation(events).split(' && '))
        self.assertIn("a3' & s2 = 0", clauses)
        self.assertIn("d4' & a3 = 0", clauses)
        self.assertNotIn('a3 = 1', clauses)
        self.assertNotIn('d4 = 1', clauses)
        self.assertNotIn('c4 = 1', clauses)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class ChainExecutionTests(unittest.TestCase):
    def test_tau_fills_two_points_and_refuses_a_broken_chain(self):
        from revise_session import revise_chain
        trace = revise_chain(TWO)
        self.assertEqual(
            [event['type'] for event in trace],
            ['session_start', 'assistant', 'tool_call', 'tool_result', 'assistant', 'session_end'],
        )
        self.assertIsNone(revise_chain(TWO, deny_call=True))
        self.assertIsNone(revise_chain(TWO, break_chain=True))


if __name__ == '__main__':
    unittest.main()
