#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_adapters import normalize_record


class LLMAdapterTests(unittest.TestCase):
    def test_hermes_tool_call_record(self):
        record = {'role': 'assistant', 'tool_calls': [{'id': 'c1', 'function': {'name': 'tau_gate'}}]}
        self.assertEqual(normalize_record(record, 'hermes'),
                         [{'type': 'assistant'}, {'type': 'tool_call', 'call_id': 'c1', 'tool': 'tau_gate'}])

    def test_claude_tool_use_record(self):
        record = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'u1', 'name': 'Bash'}]}}
        self.assertEqual(normalize_record(record, 'claude_code'),
                         [{'type': 'assistant'}, {'type': 'tool_call', 'call_id': 'u1', 'tool': 'Bash'}])

    def test_claude_tool_result_record(self):
        record = {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'u1', 'content': 'ok'}]}}
        self.assertEqual(normalize_record(record, 'claude_code'),
                         [{'type': 'tool_result', 'call_id': 'u1', 'ok': True}])

    def test_unknown_record_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_record({'role': 'system'}, 'unknown')


if __name__ == '__main__':
    unittest.main()
