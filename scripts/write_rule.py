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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, default=Path('docs/trajectories/local_session.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('docs/written_rule.json'))
    parser.add_argument('--reinstall-output', type=Path, default=Path('docs/reinstalled_rule.json'))
    args = parser.parse_args()
    written = write_rule(args.trace)
    if written is None:
        raise SystemExit('no rule')
    installed = reinstall(written['rule'])
    if installed is None:
        raise SystemExit('not reinstalled')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'fact': written['fact'], 'rule': written['rule']}, ensure_ascii=False, indent=2) + '\n')
    payload = {
        'rule': written['rule'],
        'updated': installed['updated'],
        'off': installed['off'],
    }
    args.reinstall_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({**payload, 'output': str(args.reinstall_output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
