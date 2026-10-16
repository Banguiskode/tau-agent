#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutation_matrix import summarize_matrix


class MutationMatrixTests(unittest.TestCase):
    def test_nominal_pass_and_all_mutants_rejected(self):
        report = summarize_matrix(True, [False, False, False, False])
        self.assertEqual(report, {'nominal': 'PASS', 'mutations': 4,
                                  'rejected': 4, 'status': 'PASS'})

    def test_accepted_mutation_fails_matrix(self):
        report = summarize_matrix(True, [False, True])
        self.assertEqual(report['rejected'], 1)
        self.assertEqual(report['status'], 'FAIL')

    def test_invalid_nominal_fails_matrix(self):
        self.assertEqual(summarize_matrix(False, [False])['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
