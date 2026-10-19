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


def chain_clause(events: list[dict], point: int) -> str | None:
    """Le second maillon déjà écrit. Il n'épingle pas la fin."""
    body = [event for event in events if event['type'] != 'session_start']
    result_at = next((index for index, event in enumerate(body) if event['type'] == 'tool_result'), None)
    if result_at is None:
        return None
    decision_at = result_at + 1
    end_at = result_at + 2
    if end_at != point or decision_at >= len(body):
        return None
    return f"d{end_at}' & a{decision_at} = 0"


def joint_laws(events: list[dict], later: int, timeout: int = 20) -> dict | None:
    """Les deux lois, sans épingler le pas que la première révise."""
    body = [event for event in events if event['type'] != 'session_start']
    earlier = later - 1
    result_at = later - 2
    if result_at < 0 or body[result_at]['type'] != 'tool_result':
        return None
    kind = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
    parts: list[str] = []
    for time in range(later + 1):
        names = [f'{bit}{time}' for bit in 'acsd']
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
    for time, event in enumerate(body[:result_at + 1]):
        chosen = kind[event['type']]
        for bit in 'acsd':
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
    if f'a{earlier} = 1' in parts or f'd{later} = 1' in parts:
        return None
    equation = ' && '.join(parts) + f" && d{earlier}' & s{result_at} = 0 && d{later}' & a{earlier} = 0"
    printed = normalized_clause(equation, timeout)
    if printed is None:
        return None
    conjuncts = set(printed.split(' && '))
    if f"d{earlier}' = 0" not in conjuncts or f'a{earlier} = 0' not in conjuncts:
        return None
    if f"d{later}' = 0" in conjuncts:
        return None
    ran = execute_on(BIT_STREAM['d'], earlier, timeout)
    if ran is None or ran['value'] != 1:
        return None
    revised = revised_prefix(events, earlier, 'session_end')
    if revised is None or not violation_closed(revised, timeout):
        return None
    return {
        'point': earlier,
        'event': 'session_end',
        'elected': f"d{earlier}' = 0",
        'assistant_off': f'a{earlier} = 0',
        'later_forced': False,
        'revised': revised,
    }


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


LAWS = {'n0': 'stop_after_result', 'n1': 'no_second_call'}


def law_equation(events: list[dict], ban: int, next_type: str) -> str:
    """Tau choisit la loi. `n0 = 1` et `n1 = 1` ne sont pas des clauses."""
    kind = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
    observed = kind[next_type]
    parts = [
        keep_equation(events, ban, next_type),
        'n0 & n1 = 0',
        'n0 | n1 = 1',
        f"n0 & s{ban - 1}' = 0",
        f"n0 & d{ban}' = 0",
        f'{observed}{ban + 1} = 1',
    ]
    for bit in 'acsd':
        if bit != observed:
            parts.append(f'{bit}{ban + 1} = 0')
    parts.append(f"n1 & c{ban + 1}' = 0")
    parts.append('n1 & m = 0')
    parts.append(f'n1 & c{ban} = 0')
    return ' && '.join(parts)


def choose_law(path: Path, timeout: int = 20) -> dict | None:
    events = load_events(path)
    ban = second_decision(events)
    body = [event for event in events if event['type'] != 'session_start']
    if ban is None or ban + 1 >= len(body):
        return None
    written = write_rule(path, timeout=timeout)
    if written is None:
        return None
    installed = reinstall(written['rule'], timeout=timeout)
    if installed is None or ban not in installed['off']:
        return None
    next_type = body[ban + 1]['type']
    equation = law_equation(events, ban, next_type)
    witness = solve_assignments(equation, timeout)
    if witness is None:
        return None
    chosen_laws = [LAWS[name] for name in LAWS if witness.get(name) == 1]
    chosen = [bit for bit in 'acsd' if witness.get(f'{bit}{ban}') == 1]
    if len(chosen_laws) != 1 or len(chosen) != 1 or witness.get('m') not in (0, 1):
        raise RuntimeError(f'law choice is not one pair: {chosen_laws} {chosen}')
    legal = [
        LAWS[name]
        for name in LAWS
        if solve_assignments(equation + f' && {name} = 1', timeout) is not None
    ]
    return {
        'point': ban,
        'recorded_next': next_type,
        'law': chosen_laws[0],
        'legal': legal,
        'free': 'keep' if witness.get('m') == 1 else 'discard',
        'free_event': EVENT[chosen[0]],
    }


def violation_fact(events: list[dict]) -> str | None:
    """Le fait observé, pas la loi. Après un résultat, le pas n'est pas une fin."""
    body = [event for event in events if event['type'] != 'session_start']
    for index, event in enumerate(body):
        if index and body[index - 1]['type'] == 'tool_result' and event['type'] != 'session_end':
            return "o3[t] & o5[t]' != 0."
    return None


def bind_reason(rule: str, ban: int) -> str:
    """Le booléen vient de la clause imprimée. `sometimes` ne passe pas dans `solve`."""
    clause = installable(rule).replace('sometimes ', '').strip().rstrip('.')
    return clause.replace('o5[t]', f'd{ban}').replace('o3[t]', f's{ban - 1}')


def apply_written_reason(path: Path, timeout: int = 20) -> dict | None:
    events = load_events(path)
    fact = violation_fact(events)
    ban = second_decision(events)
    body = [event for event in events if event['type'] != 'session_start']
    if fact is None or ban is None or ban + 1 >= len(body):
        return None
    written = write_rule(path, fact=fact, timeout=timeout)
    if written is None or 'sometimes' not in written['rule']:
        return None
    if written['rule'] in written['script'] or 'sometimes' in written['script']:
        return None
    clause = bind_reason(written['rule'], ban)
    if f'd{ban}' not in clause or f's{ban - 1}' not in clause:
        return None
    next_type = body[ban + 1]['type']
    equation = keep_equation(events, ban, next_type) + ' && ' + clause
    free = solve_assignments(equation, timeout)
    if free is None or free.get('m') not in (0, 1):
        return None
    chosen = [bit for bit in 'acsd' if free.get(f'{bit}{ban}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'written reason is not one event: {chosen}')
    return {
        'point': ban,
        'fact': fact,
        'rule': written['rule'],
        'clause': clause,
        'recorded_next': next_type,
        'free': 'keep' if free.get('m') == 1 else 'discard',
        'free_event': EVENT[chosen[0]],
        'keep_possible': solve_assignments(equation + ' && m = 1', timeout) is not None,
        'discard_possible': solve_assignments(equation + ' && m = 0', timeout) is not None,
    }


VIOLATIONS = {'v0': 'result_then_not_end', 'v1': 'second_call'}
STREAM = {'assistant': 'o2', 'tool_result': 'o3', 'tool_call': 'o4', 'session_end': 'o5'}
STREAM_BIT = {'o2': 'a', 'o3': 's', 'o4': 'c', 'o5': 'd'}
BIT_STREAM = {bit: stream for stream, bit in STREAM_BIT.items()}


def violation_equation(events: list[dict]) -> str:
    """Tau nomme la violation. `v0 = 1`, `v1 = 1` et `p3 = 1` ne sont pas des clauses."""
    kind = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
    body = [event for event in events if event['type'] != 'session_start']
    parts = ['v0 & v1 = 0', 'v0 | v1 = 1']
    for time, event in enumerate(body):
        chosen = kind[event['type']]
        for bit in 'acsd':
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
        if time == 0:
            parts.append(f'v0 & p{time} = 0')
            parts.append(f'v1 & p{time} = 0')
        else:
            parts.append(f"v0 & p{time} & s{time - 1}' = 0")
            parts.append(f'v0 & p{time} & d{time} = 0')
            earlier = ' & '.join(f"c{index}'" for index in range(time))
            parts.append(f'v1 & p{time} & {earlier} = 0')
        parts.append(f"v1 & p{time} & c{time}' = 0")
    parts.append(' | '.join(f'p{time}' for time in range(len(body))) + ' = 1')
    for left in range(len(body)):
        for right in range(left + 1, len(body)):
            parts.append(f'p{left} & p{right} = 0')
    return ' && '.join(parts)


def bind_named(rule: str, point: int) -> str:
    clause = installable(rule).replace('sometimes ', '').strip().rstrip('.')
    return (
        clause.replace('o5[t]', f'd{point}')
        .replace('o3[t]', f's{point - 1}')
        .replace('o4[t]', f'c{point}')
    )


def named_apply_equation(events: list[dict], point: int, clause: str) -> str:
    kind = {'assistant': 'a', 'tool_call': 'c', 'tool_result': 's', 'session_end': 'd'}
    body = [event for event in events if event['type'] != 'session_start']
    parts: list[str] = []
    for time in range(point + 1):
        names = [f'{bit}{time}' for bit in 'acsd']
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                parts.append(f'{left} & {right} = 0')
        parts.append(' | '.join(names) + ' = 1')
    for time, event in enumerate(body[:point]):
        chosen = kind[event['type']]
        for bit in 'acsd':
            parts.append(f'{bit}{time} = {1 if bit == chosen else 0}')
    bit = kind[body[point]['type']]
    parts.append(f"m & {bit}{point}' = 0")
    parts.append(f"m' & {bit}{point} = 0")
    parts.append(f'({clause})')
    return ' && '.join(parts)


def observation_formula(events: list[dict], point: int) -> tuple[str, dict[str, str]] | None:
    """Les bits du pas nommé et du pas d'avant. Pas une phrase par sorte."""
    body = [event for event in events if event['type'] != 'session_start']
    binding: dict[str, str] = {}
    terms: list[str] = []
    for time in (point, point - 1):
        if time < 0:
            continue
        stream = STREAM[body[time]['type']]
        if stream in binding:
            return None
        binding[stream] = f'{STREAM_BIT[stream]}{time}'
        terms.append(f'{stream}[t] = 1')
    return ' && '.join(terms), binding


def bind_printed(rule: str, binding: dict[str, str]) -> str:
    clause = installable(rule).replace('sometimes ', '').strip().rstrip('.')
    for stream, bit in sorted(binding.items(), key=lambda item: -len(item[0])):
        clause = clause.replace(f'{stream}[t]', bit)
    return clause


def printed_fact(formula: str, timeout: int = 20) -> str | None:
    """La phrase est la ligne `%1:`. Si elle manque ou recopie l'entrée, rien."""
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=f'n {formula}\nquit\n',
        capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Syntax Error' in output or 'Failed to parse' in output:
        return None
    for line in output.splitlines():
        if line.startswith('%1:'):
            phrase = line.split('%1:', 1)[1].strip()
            if phrase and phrase != formula and 'always' in phrase:
                return phrase
    return None


def normalized_clause(equation: str, timeout: int = 20) -> str | None:
    """La clause nécessaire est la ligne `%1:`. Si elle recopie l'entrée, rien."""
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=f'n {equation}\nquit\n',
        capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Syntax Error' in output or 'Failed to parse' in output:
        return None
    for line in output.splitlines():
        if line.startswith('%1:'):
            phrase = line.split('%1:', 1)[1].strip()
            if phrase and phrase != equation:
                return phrase
    return None


ASSIGNED = re.compile(r'(o\d+)\[(\d+)\] := (\S+)')
UNBOUND = re.compile(r"x\d+'?")


def execute_rule(rule: str, pin: str | None = None, timeout: int = 20) -> dict | None:
    """Un `x` dans l'exécution n'est pas un bit. On ne le convertit pas."""
    line = installable(rule)
    streams = sorted(set(re.findall(r'o\d+', line)))
    if pin:
        streams = sorted(set(streams) | {pin})
    if not streams:
        return None
    if not line.endswith('.'):
        line += '.'
    run = f'run {pin}[t] = 1 && u[0] = i1[0]\n' if pin else 'run u[0] = i1[0]\n'
    script = ''.join(f'{name}:sbf := out console.\n' for name in streams)
    script += run + line + '\n# step\nq\nquit\n'
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=script, capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Updated specification' not in output or 'Incompatible type' in output:
        return None
    rows = []
    for name, step, value in ASSIGNED.findall(output):
        if value in ('0', '1'):
            rows.append({'stream': name, 'step': int(step), 'value': int(value), 'unbound': False})
        elif UNBOUND.fullmatch(value):
            rows.append({'stream': name, 'step': int(step), 'value': value, 'unbound': True})
        else:
            return None
    if not rows:
        return None
    unbound = [f"{row['stream']}[{row['step']}]" for row in rows if row['unbound']]
    return {'rows': rows, 'unbound': unbound, 'replacement_executed': not unbound}


def execute_printed(stream: str, step: int, timeout: int = 20) -> dict | None:
    """La clause de `n`, à son indice. Les autres zéros ne sont pas lus."""
    clause = f"{stream}[{step}]' != 0"
    script = f'{stream}:sbf := out console.\nrun {clause}\n# step\nq\nquit\n'
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=script, capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Error' in output or 'unsat' in output or f'{stream}[{step}]:sbf' not in output:
        return None
    match = re.search(rf'{stream}\[{step}\] := (\S+)', output)
    if match is None or UNBOUND.fullmatch(match.group(1)) or match.group(1) not in ('0', '1'):
        return None
    return {'clause': clause, 'value': int(match.group(1))}


def execute_on(stream: str, step: int, timeout: int = 20) -> dict | None:
    """Le bit forcé allumé, à son indice. Les autres pas ne sont pas lus."""
    clause = f"{stream}[{step}]' = 0"
    script = f'{stream}:sbf := out console.\nrun {clause}\n# step\nq\nquit\n'
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=script, capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Error' in output or 'unsat' in output or f'{stream}[{step}]:sbf' not in output:
        return None
    match = re.search(rf'{stream}\[{step}\] := (\S+)', output)
    if match is None or UNBOUND.fullmatch(match.group(1)) or match.group(1) not in ('0', '1'):
        return None
    return {'clause': clause, 'value': int(match.group(1))}


def open_replacement(off_stream: str, step: int, candidates: list[str], timeout: int = 20) -> dict | None:
    """Un 1 d'exécution n'est pas l'événement si un autre flux peut être allumé."""
    if len(candidates) < 2:
        return None
    decls = ''.join(f'{name}:sbf := out console.\n' for name in [off_stream, *candidates])
    parts = [f"{off_stream}[{step}]' != 0"]
    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            parts.append(f'{left}[{step}] & {right}[{step}] = 0')
    parts.append(' | '.join(f'{name}[{step}]' for name in candidates) + ' = 1')
    base = ' && '.join(parts)

    def once(extra: str = '') -> dict[str, int] | None:
        script = decls + f'run {base}{extra}\n# step\nq\nquit\n'
        result = subprocess.run(
            ['tau', '-X', '-q', '-c', 'false'],
            input=script, capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout + result.stderr
        if 'Error' in output or 'unsat' in output:
            return None
        found = {}
        for name in candidates:
            match = re.search(rf'{name}\[{step}\] := (\S+)', output)
            if match is None or match.group(1) not in ('0', '1'):
                return None
            found[name] = int(match.group(1))
        return found

    free = once()
    if free is None:
        return None
    on = [name for name, value in free.items() if value == 1]
    if len(on) != 1:
        return None
    legal = [
        name for name in candidates
        if (forced := once(f' && {name}[{step}] = 1')) is not None and forced.get(name) == 1
    ]
    if not legal:
        return None
    return {'model': on[0], 'legal': legal, 'forced': len(legal) == 1}


def revised_prefix(events: list[dict], point: int, event_type: str | None) -> list[dict] | None:
    """Le pas écrit n'a que le type imprimé. Pas de statut inventé, pas la suite."""
    if event_type is None:
        return None
    body = [event for event in events if event['type'] != 'session_start']
    prefix = [event for event in events if event['type'] == 'session_start'] + body[:point]
    return prefix + [{'type': event_type}]


def violation_closed(events: list[dict], timeout: int = 20) -> bool:
    """Le pas écrit n'est plus une violation seulement si Tau dit `no solution`."""
    script = f'solve {violation_equation(events)}\nquit\n'
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=script, capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    if 'Syntax Error' in output:
        raise RuntimeError(output[-500:])
    return 'no solution' in output


def fill_other(path: Path, events: list[dict], point: int, timeout: int = 20) -> dict | None:
    """Une autre violation légale. Pas le pas que le témoin a nommé."""
    observed = observation_formula(events, point)
    if observed is None:
        return None
    formula, binding = observed
    fact = printed_fact(formula, timeout)
    if fact is None:
        return None
    written = write_rule(path, fact=fact, timeout=timeout)
    if written is None or 'sometimes' not in written['rule']:
        return None
    clause = bind_printed(written['rule'], binding)
    apply_eq = named_apply_equation(events, point, clause)
    reason = reason_clause(events, point)
    if reason is None:
        return None
    printed = normalized_clause(f'{apply_eq} && {reason}', timeout)
    ons = [
        f"{bit}{point}' = 0"
        for bit in 'acsd'
        if printed and f"{bit}{point}' = 0" in set(printed.split(' && '))
    ]
    if len(ons) != 1 or ons[0] in set(apply_eq.split(' && ')):
        return None
    bit = ons[0][0]
    ran = execute_on(BIT_STREAM[bit], point, timeout)
    if ran is None or ran['value'] != 1:
        return None
    revised = revised_prefix(events, point, EVENT[bit])
    if revised is None or not violation_closed(revised, timeout):
        return None
    return {
        'point': point,
        'reason': reason,
        'elected': ons[0],
        'elected_value': ran['value'],
        'event': EVENT[bit],
        'revised': revised,
        'closed': True,
    }


def empty_step(equation: str, point: int, timeout: int = 20) -> dict | None:
    """Retirer notre un-parmi-n. L'absence n'est forcée que si `n` éteint les quatre bits."""
    bits = [f'{bit}{point}' for bit in 'acsd']
    drop = {f'{left} & {right} = 0' for index, left in enumerate(bits) for right in bits[index + 1:]}
    drop.add(' | '.join(bits) + ' = 1')
    loose = ' && '.join(part for part in equation.split(' && ') if part not in drop)
    printed = normalized_clause(loose, timeout)
    if printed is None:
        return None
    conjuncts = set(printed.split(' && '))
    forced_off = [
        f'{bit}{point}'
        for bit in 'acsd'
        if f'{bit}{point} = 0' in conjuncts or f"{bit}{point}' != 0" in conjuncts
    ]
    empty_possible = solve_assignments(
        loose + ' && ' + ' && '.join(f'{bit} = 0' for bit in bits), timeout
    ) is not None
    return {
        'forced_off': forced_off,
        'empty_possible': empty_possible,
        'empty_forced': empty_possible and len(forced_off) == 4,
    }


def printed_pairs(equation: str, length: int, timeout: int = 20) -> list[dict] | None:
    """Les paires que la clause imprimée n'interdit pas."""
    printed = normalized_clause(equation, timeout)
    if printed is None:
        return None
    conjuncts = set(printed.split(' && '))
    pairs = []
    for kind, label in VIOLATIONS.items():
        for time in range(length):
            if {f'p{time} {kind} = 0', f'{kind} p{time} = 0'} & conjuncts:
                continue
            pairs.append({'kind': label, 'point': time})
    return pairs


def revision_open(path: Path, point: int, timeout: int = 20) -> dict | None:
    """Réviser l'appel en appel est interdit. Un autre bit n'est pas pour autant élu."""
    from revise_session import point_equation, REV, REV_EVENT
    equation = point_equation(load_events(path))
    printed = normalized_clause(equation, timeout)
    if printed is None:
        return None
    conjuncts = set(printed.split(' && '))
    legal = [
        REV_EVENT[bit]
        for bit, name in REV.items()
        if solve_assignments(equation + f' && {name}{point} = 1 && p{point} = 1', timeout) is not None
    ]
    if not legal:
        return None
    ons = [REV_EVENT[bit] for bit, name in REV.items() if f"{name}{point}' = 0" in conjuncts]
    return {'legal': legal, 'forced': len(ons) == 1}


def name_violation(path: Path, timeout: int = 20) -> dict | None:
    events = load_events(path)
    body = [event for event in events if event['type'] != 'session_start']
    equation = violation_equation(events)
    witness = solve_assignments(equation, timeout)
    if witness is None:
        return None
    kinds = [name for name in VIOLATIONS if witness.get(name) == 1]
    points = [time for time in range(len(body)) if witness.get(f'p{time}') == 1]
    if len(kinds) != 1 or len(points) != 1:
        raise RuntimeError(f'violation is not one pair: {kinds} {points}')
    kind = kinds[0]
    point = points[0]
    observed = observation_formula(events, point)
    if observed is None:
        return None
    formula, binding = observed
    fact = printed_fact(formula, timeout)
    if fact is None:
        return None
    written = write_rule(path, fact=fact, timeout=timeout)
    if written is None or 'sometimes' not in written['rule']:
        return None
    if written['rule'] in written['script'] or 'sometimes' in written['script']:
        return None
    clause = bind_printed(written['rule'], binding)
    if not any(bit in clause for bit in binding.values()):
        return None
    apply_eq = named_apply_equation(events, point, clause)
    free = solve_assignments(apply_eq, timeout)
    if free is None or free.get('m') not in (0, 1):
        return None
    chosen = [bit for bit in 'acsd' if free.get(f'{bit}{point}') == 1]
    if len(chosen) != 1:
        raise RuntimeError(f'named revision is not one event: {chosen}')
    legal = []
    for name in VIOLATIONS:
        probe = solve_assignments(equation + f' && {name} = 1', timeout)
        if probe is None:
            continue
        probe_points = [time for time in range(len(body)) if probe.get(f'p{time}') == 1]
        if len(probe_points) != 1:
            raise RuntimeError(f'legal violation is not one point: {probe_points}')
        legal.append({'kind': VIOLATIONS[name], 'point': probe_points[0]})
    remaining = printed_pairs(equation, len(body), timeout)
    if remaining is None:
        return None
    decided = remaining == legal and len(remaining) == 1
    if len(remaining) == 1 and remaining != legal:
        return None
    revision = None if decided else revision_open(path, point, timeout)
    if not decided and revision is None:
        return None
    legal_events = [
        EVENT[bit]
        for bit in 'acsd'
        if solve_assignments(apply_eq + f' && {bit}{point} = 1', timeout) is not None
    ]
    printed = normalized_clause(apply_eq, timeout)
    recorded_off = f"{STREAM_BIT[STREAM[body[point]['type']]]}{point}' != 0"
    if printed is None or recorded_off not in set(printed.split(' && ')):
        return None
    if recorded_off in set(apply_eq.split(' && ')):
        return None
    executed = execute_rule(written['rule'], timeout=timeout)
    if executed is None:
        return None
    recorded_stream = next(stream for stream, bit in binding.items() if bit.endswith(str(point)))
    previous = [stream for stream in binding if stream != recorded_stream]
    if len(previous) != 1:
        return None
    pinned = execute_rule(written['rule'], pin=previous[0], timeout=timeout)
    if pinned is None:
        return None
    still = [item for item in pinned['unbound'] if item.startswith(f'{recorded_stream}[')]
    if not still:
        return None
    later_off = [
        f"{row['stream']}[{row['step']}]"
        for row in pinned['rows']
        if row['stream'] == recorded_stream and row.get('value') == 0 and row['step'] > 1
    ]
    stem = recorded_off.split("'")[0]
    bound = next(stream for stream, bit in binding.items() if bit == stem)
    fixed = execute_printed(bound, point, timeout)
    if fixed is None:
        return None
    reason = reason_clause(events, point)
    elected = None
    elected_value = None
    event = None
    if reason is not None:
        printed_reason = normalized_clause(f'{apply_eq} && {reason}', timeout)
        ons = [
            f"{bit}{point}' = 0"
            for bit in 'acsd'
            if printed_reason and f"{bit}{point}' = 0" in set(printed_reason.split(' && '))
        ]
        if len(ons) == 1 and ons[0] not in set(apply_eq.split(' && ')):
            bit = ons[0][0]
            ran = execute_on(BIT_STREAM[bit], point, timeout)
            if ran is not None and ran['value'] == 1:
                elected = ons[0]
                elected_value = ran['value']
                event = EVENT[bit]
    chain = None if event is not None else chain_clause(events, point)
    if event is None and chain is not None:
        printed_chain = normalized_clause(f'{apply_eq} && {chain}', timeout)
        ons = [
            f"{bit}{point}' = 0"
            for bit in 'acsd'
            if printed_chain and f"{bit}{point}' = 0" in set(printed_chain.split(' && '))
        ]
        if len(ons) == 1 and ons[0] not in set(apply_eq.split(' && ')):
            bit = ons[0][0]
            ran = execute_on(BIT_STREAM[bit], point, timeout)
            if ran is not None and ran['value'] == 1:
                elected = ons[0]
                elected_value = ran['value']
                event = EVENT[bit]
    settled = None
    chain_printed = None
    if chain is not None and event is not None:
        settled = joint_laws(events, point, timeout)
        if settled is not None:
            chain_printed = elected
            elected = None
            elected_value = None
            event = None
    run_model = None
    run_legal = None
    if event is None and settled is None:
        stream_of = {stream: name for name, stream in STREAM.items()}
        candidates = [STREAM[name] for name in legal_events if name != body[point]['type']]
        opened = open_replacement(recorded_stream, point, candidates, timeout)
        if opened is None:
            return None
        run_model = stream_of[opened['model']]
        run_legal = [stream_of[name] for name in opened['legal']]
        if opened['forced']:
            event = run_model
    if settled is not None:
        revised = settled['revised']
        closed = True
    else:
        revised = revised_prefix(events, point, event)
        closed = violation_closed(revised, timeout) if revised is not None else None
    vanished = empty_step(apply_eq, point, timeout) if event is None and settled is None else None
    if event is None and settled is None and vanished is None:
        return None
    others = [
        filled for item in legal
        if item['point'] != point
        and (filled := fill_other(path, events, item['point'], timeout)) is not None
    ]
    named_on = [
        f"{bit}{point}' = 0"
        for bit in 'acsd'
        if f"{bit}{point}' = 0" in set(printed.split(' && '))
    ]
    past_end = settled is not None and settled['point'] < point
    witness = None
    completed_kind = VIOLATIONS[kind]
    completed_point = point
    completed_recorded = body[point]['type']
    completed_observed = formula
    if past_end:
        witness = {
            'kind': VIOLATIONS[kind],
            'point': point,
            'recorded': body[point]['type'],
            'observed': formula,
            'printed_off': recorded_off,
            'point_clause': fixed['clause'],
            'fact': fact,
            'clause': clause,
        }
        completed = next(item for item in legal if item['point'] == settled['point'])
        completed_kind = completed['kind']
        completed_point = settled['point']
        completed_recorded = body[settled['point']]['type']
        completed_observed = observation_formula(events, settled['point'])[0]
    return {
        'kind': completed_kind,
        'point': completed_point,
        'recorded': completed_recorded,
        'past_end': past_end,
        'witness': witness,
        'legal': legal,
        'others': others,
        'printed_pairs': remaining,
        'decided': decided,
        'revision_legal': None if revision is None else revision['legal'],
        'revision_forced': None if revision is None else revision['forced'],
        'observed': completed_observed,
        'fact': None if past_end else fact,
        'rule': None if past_end else written['rule'],
        'clause': None if past_end else clause,
        'printed_off': None if past_end else recorded_off,
        'replacement_named': len(named_on) == 1,
        'unbound': executed['unbound'],
        'replacement_executed': False,
        'pinned': previous[0],
        'still_unbound': still,
        'later_off': later_off,
        'point_clause': None if past_end else fixed['clause'],
        'point_fixed': fixed['value'],
        'reason': reason,
        'chain': chain,
        'chain_printed': chain_printed,
        'settled': settled,
        'elected': elected,
        'elected_value': elected_value,
        'event': event,
        'run_model': run_model,
        'run_legal': run_legal,
        'revised': revised,
        'closed': closed,
        'empty_possible': None if vanished is None else vanished['empty_possible'],
        'empty_forced': None if vanished is None else vanished['empty_forced'],
        'model': EVENT[chosen[0]],
        'free': 'keep' if free.get('m') == 1 else 'discard',
        'legal_events': legal_events,
        'keep_possible': solve_assignments(apply_eq + ' && m = 1', timeout) is not None,
        'discard_possible': solve_assignments(apply_eq + ' && m = 0', timeout) is not None,
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
    parser.add_argument('--law-output', type=Path, default=Path('docs/chosen_law.json'))
    parser.add_argument('--written-reason-output', type=Path, default=Path('docs/written_reason.json'))
    parser.add_argument('--named-output', type=Path, default=Path('docs/named_violation.json'))
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
    chosen_law = {
        'local_session': choose_law(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': choose_law(Path('docs/trajectories/local_two_calls.jsonl')),
        'single_call': choose_law(Path('docs/trajectories/single_call.jsonl')),
    }
    if chosen_law['local_session'] is None or chosen_law['two_calls'] is None:
        raise SystemExit('law not chosen')
    if chosen_law['single_call'] is not None:
        raise SystemExit('invented a law')
    written_reason = {
        'local_session': apply_written_reason(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': apply_written_reason(Path('docs/trajectories/local_two_calls.jsonl')),
        'single_call': apply_written_reason(Path('docs/trajectories/single_call.jsonl')),
    }
    if written_reason['local_session'] is None or written_reason['two_calls'] is None:
        raise SystemExit('reason not written')
    if written_reason['single_call'] is not None:
        raise SystemExit('invented a written reason')
    named = {
        'local_session': name_violation(Path('docs/trajectories/local_session.jsonl')),
        'two_calls': name_violation(Path('docs/trajectories/local_two_calls.jsonl')),
        'single_call': name_violation(Path('docs/trajectories/single_call.jsonl')),
    }
    if named['local_session'] is None or named['two_calls'] is None:
        raise SystemExit('violation not named')
    if named['single_call'] is not None:
        raise SystemExit('invented a violation')
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
    args.law_output.write_text(json.dumps(chosen_law, ensure_ascii=False, indent=2) + '\n')
    args.written_reason_output.write_text(json.dumps(written_reason, ensure_ascii=False, indent=2) + '\n')
    args.named_output.write_text(json.dumps(named, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'named': named, 'output': str(args.named_output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
