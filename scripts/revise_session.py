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


def chain_equation(events: list[dict], deny_call: bool = False, break_chain: bool = False) -> str:
    """Deux implications après le premier résultat. Les positions ne sont pas épinglées."""
    body = [event for event in events if event['type'] != 'session_start']
    result_at = next(index for index, event in enumerate(body) if event['type'] == 'tool_result')
    prefix = body[:result_at + 1]
    decision_at = result_at + 1
    end_at = result_at + 2
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
    parts.append(f"a{decision_at}' & s{result_at} = 0")
    parts.append(f"d{end_at}' & a{decision_at} = 0")
    if deny_call:
        call_at = next(index for index, event in enumerate(prefix) if event['type'] == 'tool_call')
        parts.append(f'c{call_at} = 0')
    if break_chain:
        parts.append(f'a{decision_at} = 0')
    return ' && '.join(parts)


def revise_chain(path: Path, deny_call: bool = False, break_chain: bool = False, timeout: int = 20) -> list[dict] | None:
    events = load_events(path)
    body = [event for event in events if event['type'] != 'session_start']
    result_at = next(index for index, event in enumerate(body) if event['type'] == 'tool_result')
    witness = solve_assignments(chain_equation(events, deny_call, break_chain), timeout)
    if witness is None:
        return None
    call = next(event for event in body if event['type'] == 'tool_call')
    return events_from_window(witness, result_at + 3, call.get('call_id', 's1'))


REV = {'a': 'e', 'c': 'f', 's': 'g', 'd': 'h'}
REV_EVENT = {'a': 'assistant', 'c': 'tool_call', 's': 'tool_result', 'd': 'session_end'}


def point_window(events: list[dict]) -> list[dict]:
    body = [event for event in events if event['type'] != 'session_start']
    calls = [index for index, event in enumerate(body) if event['type'] == 'tool_call']
    last = calls[1] if len(calls) >= 2 else len(body) - 1
    return body[:last + 1]


def point_equation(events: list[dict]) -> str:
    """Tau choisit l'indice. Python n'écrit pas `p4 = 1`."""
    window = point_window(events)
    parts: list[str] = []
    for time, event in enumerate(window):
        chosen = KIND[event['type']]
        for bit in BITS:
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
        names = [f'{REV[bit]}{time}' for bit in BITS]
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
        parts.append(f"p{time} & c{time}' = 0")
        if time == 0:
            parts.append(f'p{time} = 0')
        else:
            earlier = ' & '.join(f"c{index}'" for index in range(time))
            parts.append(f'p{time} & {earlier} = 0')
        guard = ' & '.join(f"p{index}'" for index in range(time + 1))
        for bit in BITS:
            revised = f'{REV[bit]}{time}'
            recorded = f'{bit}{time}'
            parts.append(f"{guard} & {revised}' & {recorded} = 0")
            parts.append(f"{guard} & {revised} & {recorded}' = 0")
        parts.append(f'p{time} & f{time} = 0')
    parts.append(' | '.join(f'p{time}' for time in range(len(window))) + ' = 1')
    for left in range(len(window)):
        for right in range(left + 1, len(window)):
            parts.append(f'p{left} & p{right} = 0')
    return ' && '.join(parts)


def choose_point(path: Path, timeout: int = 20) -> dict | None:
    events = load_events(path)
    window = point_window(events)
    witness = solve_assignments(point_equation(events), timeout)
    if witness is None:
        return None
    chosen = [time for time in range(len(window)) if witness.get(f'p{time}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'revision point is not one index: {chosen}')
    point = chosen[0]
    revised = [{'type': 'session_start'}]
    for time, source in enumerate(window[:point + 1]):
        bits = [bit for bit in BITS if witness.get(f'{REV[bit]}{time}') == 1]
        if len(bits) != 1:
            raise RuntimeError(f'revised step {time} is not one event: {bits}')
        kind = REV_EVENT[bits[0]]
        if kind == source['type'] == 'tool_call':
            revised.append({'type': 'tool_call', 'call_id': source.get('call_id', 's1'), 'tool': source.get('tool')})
        elif kind == source['type'] == 'tool_result':
            revised.append({'type': 'tool_result', 'call_id': source.get('call_id', 's1'), 'ok': source.get('ok', True)})
        elif kind == 'session_end':
            revised.append({'type': 'session_end', 'status': 'PASS'})
        else:
            revised.append({'type': kind})
    return {
        'point': point,
        'recorded_at_point': window[point]['type'],
        'revised_at_point': revised[-1]['type'],
        'events': revised,
    }


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
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--chain', action='store_true')
    parser.add_argument('--choose', action='store_true')
    args = parser.parse_args()
    if args.choose:
        report = choose_point(Path('docs/trajectories/local_two_calls.jsonl'))
        if report is None:
            raise SystemExit('no solution')
        output = args.output or Path('docs/revision_point.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({
            'point': report['point'],
            'recorded_at_point': report['recorded_at_point'],
            'revised_at_point': report['revised_at_point'],
            'output': str(output),
        }))
        return 0
    if args.chain:
        events = revise_chain(args.trace if args.trace.name != 'local_session.jsonl' else Path('docs/trajectories/local_two_calls.jsonl'))
        output = args.output or Path('docs/trajectories/revised_two_calls.jsonl')
    else:
        events = revise_session(args.trace)
        output = args.output or Path('docs/trajectories/revised_session.jsonl')
    if events is None:
        raise SystemExit('no solution')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events))
    print(json.dumps({'events': [event['type'] for event in events], 'output': str(output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
