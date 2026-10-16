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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, default=Path('docs/trajectories/local_session.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('docs/written_rule.json'))
    args = parser.parse_args()
    written = write_rule(args.trace)
    if written is None:
        raise SystemExit('no rule')
    payload = {'fact': written['fact'], 'rule': written['rule']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({**payload, 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
