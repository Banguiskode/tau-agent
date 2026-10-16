#!/usr/bin/env python3
"""Rejeu déterministe de résultats d'outils sans rappeler les outils."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def replay_trace(events: list[dict], fixtures: dict[str, dict]) -> dict:
    errors = []
    checked = 0
    results = {e.get('call_id'): e for e in events if e.get('type') == 'tool_result'}
    for event in events:
        if event.get('type') != 'tool_call':
            continue
        call_id = event.get('call_id')
        expected = fixtures.get(call_id)
        if expected is None:
            errors.append(f'missing fixture: {call_id}')
            continue
        observed = results.get(call_id)
        if observed is None:
            errors.append(f'missing observed result: {call_id}')
            continue
        checked += 1
        for key in ('ok', 'summary'):
            if key in expected and observed.get(key) != expected[key]:
                errors.append(f'result mismatch for {call_id}: {key}')
                break
    return {'replayed': not errors, 'errors': errors, 'checked_calls': checked,
            'status': 'PASS' if not errors else 'FAIL'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('fixtures', type=Path)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    fixtures = json.loads(args.fixtures.read_text())
    report = replay_trace(events, fixtures)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['replayed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
