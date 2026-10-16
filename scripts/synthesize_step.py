#!/usr/bin/env python3
"""Le pas suivant est un témoin Tau (`solve`), pas une vérification après coup.

Dans `solve`, la juxtaposition est une conjonction : un nom de plusieurs lettres
est découpé. Les inconnues sont donc une lettre, éventuellement suivie de chiffres.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

BITS = {'a': 'assistant', 'c': 'tool_call', 'r': 'tool_result', 'd': 'session_end'}
ASSIGNMENT = re.compile(r'([A-Za-z]\d*)\s*:=\s*\{\s*([TF])\s*\}')


def step_equation(history: dict) -> str:
    parts = [
        'a & c = 0', 'a & r = 0', 'a & d = 0',
        'c & r = 0', 'c & d = 0', 'r & d = 0',
        'a | c | r | d = 1',
    ]
    if not history.get('decided'):
        parts.extend(('c = 0', 'r = 0', 'd = 0'))
    else:
        parts.append('a = 0')
        if history.get('pending'):
            parts.extend(('c = 0', 'd = 0'))
        else:
            parts.append('r = 0')
            if history.get('completed'):
                parts.append('c = 0')
    return ' && '.join(parts)


def parse_solution(text: str) -> dict | None:
    if 'no solution' in text:
        return None
    found = {name: 1 if value == 'T' else 0 for name, value in ASSIGNMENT.findall(text)}
    if not found:
        return None
    return {bit: found.get(bit, 0) for bit in BITS}


def solve(equation: str, timeout: int = 20) -> dict | None:
    script = f'solve {equation}\nquit\n'
    result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=script,
                            capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    if 'Syntax Error' in output:
        raise RuntimeError(output[-500:])
    return parse_solution(output)


def witness_event(witness: dict, call_id: str) -> dict:
    chosen = [BITS[bit] for bit, value in witness.items() if value == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'witness is not one step: {witness}')
    kind = chosen[0]
    if kind == 'tool_call':
        return {'type': 'tool_call', 'call_id': call_id, 'tool': 'tau_real_portfolio_gate'}
    if kind == 'tool_result':
        return {'type': 'tool_result', 'call_id': call_id, 'ok': True}
    if kind == 'session_end':
        return {'type': 'session_end', 'status': 'PASS'}
    return {'type': kind}


def apply_witness(history: dict, witness: dict) -> None:
    if witness.get('a'):
        history['decided'] = True
    if witness.get('c'):
        history['pending'] = True
    if witness.get('r'):
        history['pending'] = False
        history['completed'] = True
    if witness.get('d'):
        history['done'] = True


def admits(history: dict, bit: str) -> bool:
    if bit not in BITS:
        raise ValueError(f'unknown bit: {bit}')
    witness = solve(step_equation(history) + f' && {bit} = 1')
    return witness is not None and witness.get(bit) == 1


def synthesize_step(history: dict) -> dict | None:
    return solve(step_equation(history))


def synthesize_trajectory(bound: int = 6) -> list[dict]:
    history = {'decided': False, 'pending': False, 'completed': False, 'done': False}
    events = [{'type': 'session_start'}]
    for _ in range(bound):
        if history['done']:
            break
        witness = synthesize_step(history)
        if witness is None:
            raise RuntimeError('Tau has no legal next step')
        events.append(witness_event(witness, 's1'))
        apply_witness(history, witness)
    if not history['done']:
        raise RuntimeError('synthesis did not reach a terminal step')
    return events


WINDOW_KIND = {'a': 'assistant', 'c': 'tool_call', 's': 'tool_result', 'd': 'session_end'}


def window_equation(bound: int = 4, extra: tuple[str, ...] = ()) -> str:
    """Une équation, toute la fenêtre. Les positions ne sont pas épinglées."""
    if bound < 2:
        raise ValueError('window needs at least two steps')
    parts: list[str] = []
    for t in range(bound):
        names = [f'{bit}{t}' for bit in 'acsd']
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
    parts.extend(('c0 = 0', 's0 = 0', 'd0 = 0'))
    for t in range(1, bound):
        prior_a = ' & '.join(f"a{i}'" for i in range(t))
        prior_c = ' & '.join(f"c{i}'" for i in range(t))
        prior_s = ' & '.join(f"s{i}'" for i in range(t))
        parts.append(f'c{t} & {prior_a} = 0')
        parts.append(f's{t} & {prior_c} = 0')
        parts.append(f'd{t} & {prior_s} = 0')
    for bit in 'acsd':
        names = [f'{bit}{t}' for t in range(bound)]
        parts.append(' | '.join(names) + ' = 1')
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
    parts.extend(extra)
    return ' && '.join(parts)


def parse_assignments(text: str) -> dict | None:
    if 'no solution' in text:
        return None
    found = {name: 1 if value == 'T' else 0 for name, value in ASSIGNMENT.findall(text)}
    return found or None


def solve_assignments(equation: str, timeout: int = 20) -> dict | None:
    script = f'solve {equation}\nquit\n'
    result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=script,
                            capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    if 'Syntax Error' in output:
        raise RuntimeError(output[-500:])
    return parse_assignments(output)


def events_from_window(witness: dict, bound: int = 4, call_id: str = 'w1') -> list[dict]:
    events = [{'type': 'session_start'}]
    for t in range(bound):
        chosen = [bit for bit in 'acsd' if witness.get(f'{bit}{t}') == 1]
        if len(chosen) != 1:
            raise RuntimeError(f'window step {t} is not one event: {witness}')
        kind = WINDOW_KIND[chosen[0]]
        if kind == 'tool_call':
            events.append({'type': 'tool_call', 'call_id': call_id, 'tool': 'tau_real_portfolio_gate'})
        elif kind == 'tool_result':
            events.append({'type': 'tool_result', 'call_id': call_id, 'ok': True})
        elif kind == 'session_end':
            events.append({'type': 'session_end', 'status': 'PASS'})
            break
        else:
            events.append({'type': kind})
    if events[-1]['type'] != 'session_end':
        raise RuntimeError('window witness has no terminal step')
    return events


def synthesize_window(bound: int = 4, extra: tuple[str, ...] = ()) -> list[dict] | None:
    witness = solve_assignments(window_equation(bound, extra))
    if witness is None:
        return None
    return events_from_window(witness, bound)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--bound', type=int, default=6)
    parser.add_argument('--window', action='store_true')
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    if args.window:
        events = synthesize_window()
        if events is None:
            raise SystemExit('no solution')
        output = args.output or Path('docs/trajectories/synthesized_window.jsonl')
    else:
        events = synthesize_trajectory(args.bound)
        output = args.output or Path('docs/trajectories/synthesized.jsonl')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events))
    print(json.dumps({'events': [event['type'] for event in events], 'output': str(output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
