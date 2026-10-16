#!/usr/bin/env python3
"""Révision par point : le flux `u` fusionne ou refuse, le harness n'invente pas.

Une proposition insatisfiable rend `u := F` et n'est pas appliquée. Une
proposition satisfiable est fusionnée ; le pas suivant, pas le pas de la
mise à jour, obéit à la loi nouvelle.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

EXCLUSION = ' && '.join((
    'a[t] & c[t] = 0', 'a[t] & s[t] = 0', 'a[t] & d[t] = 0',
    'c[t] & s[t] = 0', 'c[t] & d[t] = 0', 's[t] & d[t] = 0',
    'a[t] | c[t] | s[t] | d[t] = 1',
))
PROPOSALS = (EXCLUSION, 'c[t] = 0 && c[t] = 1', 'a[t] = 1')
STEP_RE = re.compile(r'Execution step: (\d+)')
BIT_RE = re.compile(r'^([acsd])\[\d+\]\s*:=\s*([01])\s*$', re.M)
U_RE = re.compile(r'^u\[\d+\]\s*:=\s*(.+?)\s*$', re.M)
UPDATED_RE = re.compile(r'^Updated specification \(\d+ chars\): (.+)$', re.M)


def revision_script(proposals: list[str] | tuple[str, ...] = PROPOSALS) -> str:
    links = ' && '.join(f'u[{index}] = i1[{index}]' for index, _ in enumerate(proposals))
    lines = [
        'a:sbf := out console.',
        'c:sbf := out console.',
        's:sbf := out console.',
        'd:sbf := out console.',
        'spec:tau := out console.',
        f'run {links} && spec[t] = this[t]',
    ]
    lines.extend(proposal.rstrip('.') + '.' for proposal in proposals)
    lines.extend(('# step', 'q', 'quit'))
    return '\n'.join(lines) + '\n'


def parse_revision(text: str) -> list[dict]:
    marks = list(STEP_RE.finditer(text))
    steps = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        block = text[mark.end():end]
        bits = {name: int(value) for name, value in BIT_RE.findall(block)}
        updated = UPDATED_RE.search(block)
        u_match = U_RE.search(block)
        u_value = u_match.group(1) if u_match else ''
        steps.append({
            'step': int(mark.group(1)),
            'accepted': updated is not None,
            'u': u_value,
            'bits': bits,
            'one_hot': sum(bits.values()) == 1 if bits else False,
            'updated': updated.group(1) if updated else '',
        })
    return steps


def run_revision(script: str, timeout: int = 30) -> str:
    result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=script,
                            capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    if 'Syntax Error' in output:
        raise RuntimeError(output[-500:])
    return output


def revise(proposals: tuple[str, ...] = PROPOSALS, timeout: int = 30) -> dict:
    output = run_revision(revision_script(proposals), timeout)
    steps = parse_revision(output)
    if not steps:
        raise RuntimeError(output[-500:])
    return {'steps': steps, 'proposals': len(proposals)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('docs/revision_report.json'))
    args = parser.parse_args()
    report = revise()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({
        'steps': len(report['steps']),
        'accepted': sum(1 for step in report['steps'] if step['accepted']),
        'refused': sum(1 for step in report['steps'] if step['u'] == 'F'),
        'output': str(args.output),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
