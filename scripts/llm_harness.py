#!/usr/bin/env python3
"""Harness minimal et indépendant pour rejouer les traces d'un agent LLM."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ALLOWED_TYPES = {'session_start', 'assistant', 'tool_call', 'tool_result', 'session_end'}


def validate_trace(events: list[dict], allowed_tools: set[str], max_steps: int = 100) -> dict:
    errors: list[str] = []
    pending: dict[str, str] = {}
    tool_calls = 0
    terminal = False
    if not events or events[0].get('type') != 'session_start':
        errors.append('trace must start with session_start')
    for index, event in enumerate(events):
        kind = event.get('type')
        if kind not in ALLOWED_TYPES:
            errors.append(f'unknown event type at {index}: {kind}')
            continue
        if kind == 'tool_call':
            tool_calls += 1
            tool = event.get('tool')
            call_id = event.get('call_id')
            if tool not in allowed_tools:
                errors.append(f'disallowed tool at {index}: {tool}')
            if not call_id:
                errors.append(f'missing call_id at {index}')
            elif call_id in pending:
                errors.append(f'duplicate call_id at {index}: {call_id}')
            else:
                pending[call_id] = tool or ''
            if tool_calls > max_steps:
                errors.append(f'max tool steps exceeded: {max_steps}')
        elif kind == 'tool_result':
            call_id = event.get('call_id')
            if call_id not in pending:
                errors.append(f'orphan tool_result at {index}: {call_id}')
            else:
                del pending[call_id]
        elif kind == 'session_end':
            terminal = True
            if index != len(events) - 1:
                errors.append(f'events after session_end at {index}')
    if pending:
        errors.append('unresolved tool_call: ' + ', '.join(sorted(pending)))
    if not terminal:
        errors.append('trace has no terminal session_end')
    return {'valid': not errors, 'errors': errors, 'tool_calls': tool_calls,
            'events': len(events), 'status': 'PASS' if not errors else 'FAIL'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('--allow-tool', action='append', default=[])
    parser.add_argument('--max-steps', type=int, default=100)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    report = validate_trace(events, set(args.allow_tool), args.max_steps)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
