#!/usr/bin/env python3
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revise_point import parse_revision, revision_script

FIXTURE = """
Execution step: 0
u[0] := always a[t]:sbf c[t]:sbf = 0
Updated specification (40 chars): always a[t]:sbf c[t]:sbf = 0

Execution step: 1
a[1]    := 0
c[1]    := 0
d[1]    := 0
s[1]    := 1
u[1]    := F
(Warning) An update rule was provided on input stream this but the update stream u solved to 0; the rule was not applied

Execution step: 2
a[2]    := 0
c[2]    := 0
d[2]    := 0
s[2]    := 1
u[2]    := always a[t]:sbf' = 0
Updated specification (30 chars): always a[t]:sbf' = 0 && a[t]:sbf c[t]:sbf = 0

Execution step: 3
a[3]    := 1
c[3]    := 0
d[3]    := 0
s[3]    := 0
"""


class RevisePointTests(unittest.TestCase):
    def test_parser_separates_a_refusal_from_a_merged_update(self):
        steps = parse_revision(FIXTURE)
        self.assertEqual([step['step'] for step in steps], [0, 1, 2, 3])
        self.assertTrue(steps[0]['accepted'])
        self.assertFalse(steps[1]['accepted'])
        self.assertEqual(steps[1]['u'], 'F')
        self.assertTrue(steps[1]['one_hot'])
        self.assertTrue(steps[2]['accepted'])
        self.assertIn('a[t]:sbf c[t]:sbf = 0', steps[2]['updated'])
        self.assertEqual(steps[3]['bits'], {'a': 1, 'c': 0, 's': 0, 'd': 0})

    def test_script_feeds_proposals_and_does_not_pin_the_next_step(self):
        script = revision_script(['a[t] & c[t] = 0', 'c[t] = 0 && c[t] = 1', 'a[t] = 1'])
        self.assertIn('u[0] = i1[0]', script)
        self.assertIn('u[2] = i1[2]', script)
        self.assertIn('c[t] = 0 && c[t] = 1.', script)
        self.assertNotIn('a[3]', script)
        self.assertNotIn('a[t] = 1 && a[t] = 1', script)


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class RevisePointExecutionTests(unittest.TestCase):
    def test_tau_rejects_a_contradiction_and_merges_a_refinement(self):
        from revise_point import revise
        report = revise()
        refused = next(step for step in report['steps'] if step['u'] == 'F')
        self.assertFalse(refused['accepted'])
        self.assertTrue(refused['one_hot'])
        merged = [step for step in report['steps'] if step['accepted']]
        self.assertGreaterEqual(len(merged), 2)
        self.assertIn("a[t]:sbf' = 0", merged[-1]['updated'])
        self.assertIn('a[t]:sbf d[t]:sbf = 0', merged[-1]['updated'])
        self.assertNotIn('c[t] = 0 && c[t] = 1', merged[-1]['updated'])
        after = report['steps'][-1]
        self.assertEqual(after['bits'], {'a': 1, 'c': 0, 's': 0, 'd': 0})


class OverrideTests(unittest.TestCase):
    def test_a_dropped_law_is_an_override_not_a_kept_exclusion(self):
        from revise_point import law_status
        steps = [
            {'step': 1, 'accepted': True, 'updated': "always a[t]:sbf' = 0 && a[t]:sbf d[t]:sbf = 0"},
            {'step': 2, 'accepted': True, 'updated': 'always a[t]:sbf = 0'},
            {'step': 3, 'accepted': False, 'updated': '', 'bits': {'a': 0}},
        ]
        status = law_status(steps)
        self.assertEqual(status['kind'], 'override')
        self.assertFalse(status['exclusion_kept'])
        self.assertNotIn("a[t]:sbf' = 0", status['updated'])


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class OverrideExecutionTests(unittest.TestCase):
    def test_a_satisfiable_contradiction_wins_and_drops_the_old_law(self):
        from revise_point import override
        report = override()
        self.assertEqual(report['override']['kind'], 'override')
        self.assertFalse(report['override']['exclusion_kept'])
        self.assertNotIn("a[t]:sbf' = 0", report['override']['updated'])
        self.assertIn('a[t]:sbf = 0', report['override']['updated'])
        after = next(step for step in report['steps'] if step['step'] > report['override']['step'])
        self.assertEqual(after['bits'].get('a'), 0)
        self.assertNotIn('c', after['bits'])


if __name__ == '__main__':
    unittest.main()
