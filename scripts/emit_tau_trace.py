#!/usr/bin/env python3
"""Émet un noyau Tau depuis une trace canonique, pas depuis un exemple figé.

Les faits sont des égalités ponctuelles. Un lien entre deux pas est une
implication indexée. Un prédécesseur absent est l'indice 0, déjà épinglé à 0 :
la contradiction est alors dans la spec, pas inventée.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STREAMS = ('assistant', 'tool_call', 'tool_result', 'done')
TYPE_TO_STREAM = {
    'assistant': 'assistant',
    'tool_call': 'tool_call',
    'tool_result': 'tool_result',
    'session_end': 'done',
}


def pins() -> list[str]:
    return [f'([t < 1] -> {stream}[t] = 0)' for stream in STREAMS]


def closed_world(events: list[dict]) -> list[str]:
    facts = []
    for step, event in enumerate(events, start=1):
        kind = event.get('type')
        active = TYPE_TO_STREAM.get(kind) if isinstance(kind, str) else None
        for stream in STREAMS:
            facts.append(f'{stream}[{step}] = {1 if stream == active else 0}')
    return facts


def policy_links(events: list[dict]) -> list[str]:
    links = []
    last_assistant = 0
    calls: dict[str, int] = {}
    results: list[int] = []
    for step, event in enumerate(events, start=1):
        kind = event.get('type')
        if kind == 'assistant':
            last_assistant = step
        elif kind == 'tool_call':
            links.append(f'(tool_call[{step}] = 1 -> assistant[{last_assistant}] = 1)')
            call_id = event.get('call_id')
            if isinstance(call_id, str) and call_id:
                calls[call_id] = step
        elif kind == 'tool_result':
            raw_id = event.get('call_id')
            call_t = calls.get(raw_id, 0) if isinstance(raw_id, str) else 0
            links.append(f'(tool_result[{step}] = 1 -> tool_call[{call_t}] = 1)')
            results.append(step)
        elif kind == 'session_end':
            if results:
                links.extend(f'(done[{step}] = 1 -> tool_result[{result}] = 1)' for result in results)
            else:
                links.append(f'(done[{step}] = 1 -> assistant[{last_assistant}] = 1)')
    if not links:
        raise ValueError('no policy link in trace')
    return links


def probe_pair(links: list[str]) -> tuple[str, str, str]:
    """Retourne (lien, fait antécédent, négation du conséquent)."""
    link = next(item for item in links if item.startswith('(done['))
    body = link[1:-1]
    antecedent, consequent = body.split(' -> ')
    stream, index = consequent.split('[')
    step = index.split(']')[0]
    return link, antecedent, f'{stream}[{step}] = 0'


def render_streams(streams: list[str], conjuncts: list[str]) -> str:
    declarations = '\n'.join(f'{stream} : sbf := out console.' for stream in streams)
    return f'{declarations}\nr {" && ".join(conjuncts)}\nq\nquit\n'


def order_packs(events: list[dict], pack: int = 24) -> list[tuple[list[str], list[str]]]:
    """Chaque appel est un couple (décision, appel) à t=1,2. L'indice global ne compte pas."""
    last_assistant = 0
    decided: list[bool] = []
    for step, event in enumerate(events, start=1):
        kind = event.get('type')
        if kind == 'assistant':
            last_assistant = step
        elif kind == 'tool_call':
            decided.append(last_assistant > 0)
    packs = []
    for start in range(0, len(decided), pack):
        streams: list[str] = []
        conjuncts: list[str] = []
        for offset, ok in enumerate(decided[start:start + pack]):
            assistant, call = f'a{offset}', f'c{offset}'
            streams.extend((assistant, call))
            if ok:
                conjuncts.extend((f'{assistant}[1] = 1', f'{call}[2] = 1',
                                  f'({call}[2] = 1 -> {assistant}[1] = 1)'))
            else:
                conjuncts.extend((f'([t < 1] -> {assistant}[t] = 0)', f'{call}[2] = 1',
                                  f'({call}[2] = 1 -> {assistant}[0] = 1)'))
        packs.append((streams, conjuncts))
    return packs


def slim_kernel(events: list[dict]) -> list[str]:
    """Faits positifs et liens. Un prédécesseur absent reste à l'indice 0."""
    facts = [fact for fact in closed_world(events) if fact.endswith(' = 1')]
    return pins() + facts + policy_links(events)


def negation_target(kernel: list[str], links: list[str]) -> str:
    result_facts = [fact for fact in kernel if fact.startswith('tool_result[') and fact.endswith(' = 1')]
    if result_facts:
        return result_facts[0].replace(' = 1', ' = 0')
    _, _, consequent_neg = probe_pair(links)
    positive = consequent_neg.replace(' = 0', ' = 1')
    if positive in kernel:
        return consequent_neg
    done_facts = [fact for fact in kernel if fact.startswith('done[') and fact.endswith(' = 1')]
    if done_facts:
        return done_facts[0].replace(' = 1', ' = 0')
    raise ValueError('no fact to negate')


def emit_cases(events: list[dict]) -> dict:
    if not events:
        raise ValueError('empty trace')
    links = policy_links(events)
    kernel = pins() + closed_world(events) + links
    negation = negation_target(kernel, links)
    link, antecedent, consequent_neg = probe_pair(links)
    probe = pins() + [antecedent, link]
    return {
        'kernel': {'expected': 'SAT', 'conjuncts': kernel},
        'negate_fact': {'expected': 'UNSAT', 'conjuncts': kernel + [negation]},
        'link_probe': {'expected': 'SAT', 'conjuncts': probe},
        'link_probe_neg': {'expected': 'UNSAT', 'conjuncts': probe + [consequent_neg]},
        'control_free': {'expected': 'SAT', 'conjuncts': kernel + [f'assistant[{len(events) + 1}] = 1']},
    }


def render_spec(conjuncts: list[str]) -> str:
    declarations = '\n'.join(f'{stream} : sbf := out console.' for stream in STREAMS)
    return f'{declarations}\nr {" && ".join(conjuncts)}\nq\nquit\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    cases = emit_cases(events)
    print(json.dumps({name: {'expected': case['expected'], 'conjuncts': len(case['conjuncts'])}
                      for name, case in cases.items()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
