#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_adapters import normalize_hermes_session, normalize_record
from local_traces import classify_errors, summarize_census


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

    def test_real_session_has_one_start_and_no_content(self):
        records = [
            {'role': 'user', 'content': 'secret prompt'},
            {'role': 'assistant', 'content': 'secret reply',
             'tool_calls': [{'id': 'call_1', 'function': {'name': 'terminal', 'arguments': '{"cmd":"x"}'}}]},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'secret output'},
            {'role': 'user', 'content': 'again'},
            {'role': 'session_meta', 'content': 'ignore'},
        ]
        events = normalize_hermes_session(records, ended=True, end_reason='agent_close')
        self.assertEqual([event['type'] for event in events],
                         ['session_start', 'assistant', 'tool_call', 'tool_result', 'session_end'])
        self.assertEqual(events[-1]['status'], 'agent_close')
        self.assertFalse(any('content' in event or 'arguments' in event for event in events))

    def test_open_session_has_no_terminal_event(self):
        events = normalize_hermes_session(
            [{'role': 'assistant', 'tool_calls': [{'id': 'c1', 'function': {'name': 'terminal'}}]}],
            ended=False)
        self.assertEqual(events[0]['type'], 'session_start')
        self.assertNotIn('session_end', [event['type'] for event in events])

    def test_census_summary_counts_real_failures(self):
        rows = [
            {'harness': 'PASS', 'kernel': 'SAT', 'reason': 'ok'},
            {'harness': 'FAIL', 'kernel': 'NOT_RUN', 'reason': 'unresolved tool_call'},
            {'harness': 'PASS', 'kernel': 'UNSAT', 'reason': 'ok'},
        ]
        report = summarize_census(rows)
        self.assertEqual(report['sessions'], 3)
        self.assertEqual(report['harness_pass'], 2)
        self.assertEqual(report['kernel_unsat'], 1)
        self.assertEqual(classify_errors(['unresolved tool_call: c1']), 'unresolved tool_call')

    def test_slim_kernel_keeps_the_missing_predecessor_link(self):
        from emit_tau_trace import slim_kernel
        events = [
            {'type': 'session_start'},
            {'type': 'tool_call', 'call_id': 'c1', 'tool': 'terminal'},
            {'type': 'tool_result', 'call_id': 'c1', 'ok': True},
            {'type': 'session_end'},
        ]
        kernel = slim_kernel(events)
        self.assertIn('(tool_call[2] = 1 -> assistant[0] = 1)', kernel)
        self.assertNotIn('assistant[1] = 0', kernel)
        self.assertTrue(all(not fact.endswith(' = 0') or fact.startswith('([t < 1]') for fact in kernel))

    def test_order_pack_renumbers_and_keeps_a_missing_decision(self):
        from emit_tau_trace import order_packs
        good = [
            {'type': 'session_start'},
            {'type': 'assistant'},
            {'type': 'tool_call', 'call_id': 'c1'},
            {'type': 'tool_result', 'call_id': 'c1'},
            {'type': 'session_end'},
        ]
        packs = order_packs(good, pack=24)
        self.assertEqual(len(packs), 1)
        conjuncts = packs[0][1]
        self.assertIn('(c0[2] = 1 -> a0[1] = 1)', conjuncts)
        self.assertNotIn('[3]', ' '.join(conjuncts))
        bad = [{'type': 'session_start'}, {'type': 'tool_call', 'call_id': 'c1'},
               {'type': 'session_end'}]
        bad_conjuncts = order_packs(bad)[0][1]
        self.assertIn('(c0[2] = 1 -> a0[0] = 1)', bad_conjuncts)
        self.assertIn('([t < 1] -> a0[t] = 0)', bad_conjuncts)
        many = [{'type': 'session_start'}]
        for i in range(25):
            many.extend(({'type': 'assistant'}, {'type': 'tool_call', 'call_id': f'c{i}'}))
        many.append({'type': 'session_end'})
        self.assertEqual(len(order_packs(many, pack=24)), 2)


if __name__ == '__main__':
    unittest.main()
