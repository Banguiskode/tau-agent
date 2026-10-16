#!/usr/bin/env python3
"""Tau écrit la règle : le complément du fait observé, pas une clause de la source.

Un second assistant observé est le fait `o2[t] = 1`. Tau rend le dual.
Un nom de flux illégal ne s'écrit pas : pas de règle inventée.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from synthesize_step import solve_assignments

RULE_RE = re.compile(r'o1\[0\] := (?!F\b|T\b)(.+)')


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def observed_fact(events: list[dict]) -> str | None:
    body = [event for event in events if event['type'] != 'session_start']
    decisions = [event for event in body if event['type'] == 'assistant']
    if len(decisions) < 2:
        return None
    return 'o2[t] = 1.'


def complement_script(fact: str) -> str:
    line = fact if fact.endswith('.') else fact + '.'
    return (
        'i1:tau := in console.\n'
        'o1:tau := out console.\n'
        "r o1[0] = i1[0]'\n"
        f'{line}\n'
        'q\n'
        'quit\n'
    )


def installable(rule: str) -> str:
    """L'étiquette `:tau` casse le flux sbf. On retire l'étiquette, pas la clause."""
    return rule.replace(':tau', '').strip()


def reinstall_script(rule: str) -> str:
    line = installable(rule)
    if not line.endswith('.'):
        line += '.'
    return (
        'o2:sbf := out console.\n'
        'run u[0] = i1[0]\n'
        f'{line}\n'
        '# step\n'
        'q\n'
        'quit\n'
    )


def parse_reinstall(text: str) -> dict | None:
    updated = re.search(r'Updated specification \(\d+ chars\): (.+)', text)
    if not updated:
        return None
    off = [int(step) for step, value in re.findall(r'o2\[(\d+)\] := ([01])', text) if value == '0']
    return {'updated': updated.group(1).strip(), 'off': off}


def reinstall(rule: str | None, timeout: int = 20) -> dict | None:
    if not rule:
        return None
    script = reinstall_script(rule)
    result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=script,
                            capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    if 'Failed to parse' in output or 'Syntax Error' in output:
        return None
    parsed = parse_reinstall(output)
    if parsed is None:
        return None
    parsed['script'] = script
    return parsed


def parse_written_rule(text: str) -> str | None:
    match = RULE_RE.search(text)
    if not match:
        return None
    return match.group(1).strip()


def write_rule(path: Path, fact: str | None = None, timeout: int = 20) -> dict | None:
    if fact is None:
        fact = observed_fact(load_events(path))
    if fact is None:
        return None
    script = complement_script(fact)
    result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=script,
                            capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    if 'Syntax Error' in output or 'Failed to parse' in output:
        return None
    rule = parse_written_rule(output)
    if rule is None:
        return None
    return {'fact': fact, 'rule': rule, 'script': script}


EVENT = {'a': 'assistant', 'c': 'tool_call', 's': 'tool_result', 'd': 'session_end'}


def second_decision(events: list[dict]) -> int | None:
    body = [event for event in events if event['type'] != 'session_start']
    decisions = [index for index, event in enumerate(body) if event['type'] == 'assistant']
    if len(decisions) < 2:
        return None
    return decisions[1]


def replacement_equation(events: list[dict], ban: int) -> str:
    """Le bit interdit vient de la règle réinstallée. L'événement de remplacement n'est pas épinglé."""
    body = [event for event in events if event['type'] != 'session_start']
    prefix = body[:ban]
    parts: list[str] = []
    for time in range(ban + 1):
        names = [f'{bit}{time}' for bit in 'acsd']
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
    kind = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
    for time, event in enumerate(prefix):
        chosen = kind[event['type']]
        for bit in 'acsd':
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
    parts.append(f'a{ban} = 0')
    return ' && '.join(parts)


def replace_event(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    equation = replacement_equation(events, ban)
    witness = solve_assignments(equation, timeout)
    if witness is None:
        return None
    chosen = [bit for bit in 'acsd' if witness.get(f'{bit}{ban}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'replacement is not one event: {chosen}')
    return {
        'point': ban,
        'replacement': EVENT[chosen[0]],
        'decision_still_possible': solve_assignments(
            equation.replace(f' && a{ban} = 0', '') + f' && a{ban} = 1', timeout
        ) is not None,
    }


def legal_replacements(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    equation = replacement_equation(events, ban)
    legal = []
    for bit, name in EVENT.items():
        witness = solve_assignments(equation + f' && {bit}{ban} = 1', timeout)
        if witness is not None and witness.get(f'{bit}{ban}') == 1:
            legal.append(name)
    return {'point': ban, 'legal': legal}


MISSIONS = {
    'end': ('c', 's'),
    'call': ('s', 'd'),
    'result': ('c', 'd'),
    'none': ('c', 's', 'd'),
}


def mission_equation(events: list[dict], ban: int, mission: str) -> str:
    """La mission interdit des événements. Elle n'épingle pas celui qui reste."""
    if mission not in MISSIONS:
        raise ValueError(f'unknown mission: {mission}')
    base = replacement_equation(events, ban)
    banned = ' && '.join(f'{bit}{ban} = 0' for bit in MISSIONS[mission])
    return f'{base} && {banned}'


def impose(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    chosen = {}
    for mission in MISSIONS:
        witness = solve_assignments(mission_equation(events, ban, mission), timeout)
        if witness is None:
            chosen[mission] = None
            continue
        bits = [bit for bit in 'acsd' if witness.get(f'{bit}{ban}') == 1]
        if len(bits) != 1:
            raise RuntimeError(f'{mission} is not one event: {bits}')
        chosen[mission] = EVENT[bits[0]]
    return {'point': ban, 'chosen': chosen}


DRAW_BANS = {'c': 'x0', 's': 'x1', 'd': 'x2'}
DRAW_NAME = {'x0': 'tool_call', 'x1': 'tool_result', 'x2': 'session_end'}
DRAW_BIT = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}


def drawn_equation(events: list[dict], ban: int, next_type: str) -> str:
    """Le trajet épingle le pas suivant. Tau remplit les interdits."""
    bit = DRAW_BIT[next_type]
    equation = replacement_equation(events, ban) + f' && {bit}{ban} = 1'
    for event_bit, name in DRAW_BANS.items():
        equation += f" && {name} & {event_bit}{ban} = 0 && {name}' & {event_bit}{ban}' = 0"
    return equation


def draw_mission(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    body = [event for event in events if event['type'] != 'session_start']
    if ban + 1 >= len(body):
        return None
    next_type = body[ban + 1]['type']
    witness = solve_assignments(drawn_equation(events, ban, next_type), timeout)
    if witness is None:
        return None
    return {
        'point': ban,
        'recorded_next': next_type,
        'banned': [DRAW_NAME[name] for name in DRAW_BANS.values() if witness.get(name) == 1],
        'kept': [DRAW_NAME[name] for name in DRAW_BANS.values() if witness.get(name) == 0],
    }


def keep_equation(events: list[dict], ban: int, next_type: str) -> str:
    """`m` lie le pas révisé au pas enregistré. `m` n'est pas épinglé."""
    bit = DRAW_BIT[next_type]
    return (
        replacement_equation(events, ban)
        + f" && m & {bit}{ban}' = 0 && m' & {bit}{ban} = 0"
    )


def decide_keep(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    body = [event for event in events if event['type'] != 'session_start']
    if ban + 1 >= len(body):
        return None
    next_type = body[ban + 1]['type']
    equation = keep_equation(events, ban, next_type)
    free = solve_assignments(equation, timeout)
    if free is None or free.get('m') not in (0, 1):
        return None
    kept = solve_assignments(equation + ' && m = 1', timeout)
    discarded = solve_assignments(equation + ' && m = 0', timeout)
    decision = solve_assignments(equation + ' && a' + str(ban) + ' = 1 && m = 1', timeout)
    chosen = [bit for bit in 'acsd' if free.get(f'{bit}{ban}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'free choice is not one event: {chosen}')
    return {
        'point': ban,
        'recorded_next': next_type,
        'free': 'keep' if free.get('m') == 1 else 'discard',
        'free_event': EVENT[chosen[0]],
        'keep_possible': kept is not None,
        'discard_possible': discarded is not None,
        'keep_decision': decision is not None,
    }


def reason_clause(events: list[dict], ban: int) -> str | None:
    """La loi déjà écrite : après un résultat, on s'arrête."""
    body = [event for event in events if event['type'] != 'session_start']
    if ban == 0 or body[ban - 1]['type'] != 'tool_result':
        return None
    return f"d{ban}' & s{ban - 1} = 0"


def reason_equation(events: list[dict], ban: int, next_type: str) -> str:
    clause = reason_clause(events, ban)
    if clause is None:
        raise RuntimeError('no result before the point')
    return keep_equation(events, ban, next_type) + ' && ' + clause


def reasoned_keep(path: Path, timeout: int = 20) -> dict | None:
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None:
        return None
    events = load_events(path)
    ban = second_decision(events)
    if ban is None or ban not in installed['off']:
        return None
    body = [event for event in events if event['type'] != 'session_start']
    if ban + 1 >= len(body):
        return None
    clause = reason_clause(events, ban)
    if clause is None:
        return None
    equation = reason_equation(events, ban, body[ban + 1]['type'])
    free = solve_assignments(equation, timeout)
    if free is None or free.get('m') not in (0, 1):
        return None
    chosen = [bit for bit in 'acsd' if free.get(f'{bit}{ban}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'reasoned choice is not one event: {chosen}')
    return {
        'point': ban,
        'recorded_next': body[ban + 1]['type'],
        'reason': clause,
        'free': 'keep' if free.get('m') == 1 else 'discard',
        'free_event': EVENT[chosen[0]],
        'keep_possible': solve_assignments(equation + ' && m = 1', timeout) is not None,
        'discard_possible': solve_assignments(equation + ' && m = 0', timeout) is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, default=Path('docs/trajectories/local_session.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('docs/written_rule.json'))
    parser.add_argument('--reinstall-output', type=Path, default=Path('docs/reinstalled_rule.json'))
    parser.add_argument('--replacement-output', type=Path, default=Path('docs/replacement.json'))
    parser.add_argument('--legal-output', type=Path, default=Path('docs/legal_replacements.json'))
    parser.add_argument('--mission-output', type=Path, default=Path('docs/imposed.json'))
    parser.add_argument('--drawn-output', type=Path, default=Path('docs/drawn_mission.json'))
    parser.add_argument('--keep-output', type=Path, default=Path('docs/keep_decision.json'))
    parser.add_argument('--reason-output', type=Path, default=Path('docs/reasoned_keep.json'))
    args = parser.parse_args()
    written = write_rule(args.trace)
    if written is None:
        raise SystemExit('no rule')
    installed = reinstall(written['rule'])
    if installed is None:
        raise SystemExit('not reinstalled')
    replaced = replace_event(args.trace)
    if replaced is None:
        raise SystemExit('no replacement')
    legal = legal_replacements(args.trace)
    if legal is None:
        raise SystemExit('no legal set')
    imposed = impose(args.trace)
    if imposed is None:
        raise SystemExit('no mission')
    drawn = {
        'local_session': draw_mission(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': draw_mission(Path('docs/trajectories/local_two_calls.jsonl')),
    }
    if drawn['local_session'] is None or drawn['two_calls'] is None:
        raise SystemExit('mission not drawn')
    decided = {
        'local_session': decide_keep(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': decide_keep(Path('docs/trajectories/local_two_calls.jsonl')),
    }
    if decided['local_session'] is None or decided['two_calls'] is None:
        raise SystemExit('keep not decided')
    reasoned = {
        'local_session': reasoned_keep(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': reasoned_keep(Path('docs/trajectories/local_two_calls.jsonl')),
    }
    if reasoned['local_session'] is None or reasoned['two_calls'] is None:
        raise SystemExit('reason not applied')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'fact': written['fact'], 'rule': written['rule']}, ensure_ascii=False, indent=2) + '\n')
    args.reinstall_output.write_text(json.dumps({
        'rule': written['rule'],
        'updated': installed['updated'],
        'off': installed['off'],
    }, ensure_ascii=False, indent=2) + '\n')
    args.replacement_output.write_text(json.dumps(replaced, ensure_ascii=False, indent=2) + '\n')
    args.legal_output.write_text(json.dumps(legal, ensure_ascii=False, indent=2) + '\n')
    args.mission_output.write_text(json.dumps(imposed, ensure_ascii=False, indent=2) + '\n')
    args.drawn_output.write_text(json.dumps(drawn, ensure_ascii=False, indent=2) + '\n')
    args.keep_output.write_text(json.dumps(decided, ensure_ascii=False, indent=2) + '\n')
    args.reason_output.write_text(json.dumps(reasoned, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'reason': reasoned, 'output': str(args.reason_output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
