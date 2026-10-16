#!/usr/bin/env python3
"""Révision au milieu d'une session réelle.

Le préfixe observé est épinglé. La loi nouvelle est une implication, pas le
témoin. `u` n'est pas ce chemin : un pin `c[1]` y a été réécrit, mesuré.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from synthesize_step import events_from_window, solve_assignments

KIND = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
BITS = 'acsd'


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def session_equation(events: list[dict], deny_call: bool = False) -> str:
    body = [event for event in events if event['type'] != 'session_start']
    result_at = next(index for index, event in enumerate(body) if event['type'] == 'tool_result')
    prefix = body[:result_at + 1]
    end_at = result_at + 1
    parts: list[str] = []
    for time in range(end_at + 1):
        names = [f'{bit}{time}' for bit in BITS]
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
    for time, event in enumerate(prefix):
        chosen = KIND[event['type']]
        for bit in BITS:
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
    parts.append(f"d{end_at}' & s{result_at} = 0")
    if deny_call:
        call_at = next(index for index, event in enumerate(prefix) if event['type'] == 'tool_call')
        parts.append(f'c{call_at} = 0')
    return ' && '.join(parts)


def revise_session(path: Path, deny_call: bool = False, timeout: int = 20) -> list[dict] | None:
    events = load_events(path)
    body = [event for event in events if event['type'] != 'session_start']
    result_at = next(index for index, event in enumerate(body) if event['type'] == 'tool_result')
    witness = solve_assignments(session_equation(events, deny_call), timeout)
    if witness is None:
        return None
    call = next(event for event in body if event['type'] == 'tool_call')
    return events_from_window(witness, result_at + 2, call.get('call_id', 's1'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, default=Path('docs/trajectories/local_session.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('docs/trajectories/revised_session.jsonl'))
    args = parser.parse_args()
    events = revise_session(args.trace)
    if events is None:
        raise SystemExit('no solution')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events))
    print(json.dumps({'events': [event['type'] for event in events], 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
