#!/usr/bin/env python3
"""Mutations négatives d'une trace LLM pour tester les portes du harness."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path

MUTATIONS = ('disallowed_tool', 'orphan_result', 'early_stop', 'ignored_result')


def mutate_trace(events: list[dict], mutation: str) -> list[dict]:
    if mutation not in MUTATIONS:
        raise ValueError(f'unknown mutation: {mutation}')
    result = copy.deepcopy(events)
    if mutation == 'disallowed_tool':
        for event in result:
            if event.get('type') == 'tool_call':
                event['tool'] = 'forbidden_tool'
                return result
    elif mutation == 'orphan_result':
        return [e for e in result if e.get('type') != 'tool_call']
    elif mutation == 'ignored_result':
        return [e for e in result if e.get('type') != 'tool_result']
    elif mutation == 'early_stop':
        return [e for e in result if e.get('type') != 'session_end']
    raise ValueError(f'mutation has no applicable event: {mutation}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('mutation', choices=MUTATIONS)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    mutated = mutate_trace(events, args.mutation)
    with args.output.open('w', encoding='utf-8') as stream:
        for event in mutated:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(json.dumps({'mutation': args.mutation, 'events': len(mutated),
                      'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
