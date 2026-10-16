#!/usr/bin/env python3
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_rule import complement_script, parse_written_rule

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


if __name__ == '__main__':
    unittest.main()
