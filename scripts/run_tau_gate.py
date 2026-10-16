#!/usr/bin/env python3
"""Exécute la propriété Tau de la transition agent et sa mutation."""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path


def classify(output: str) -> str:
    if 'Syntax Error' in output: return 'SYNTAX'
    if 'Tau specification is unsat' in output or 'result: F' in output: return 'UNSAT'
    if 'Execution step:' in output and 'run:' in output: return 'SAT'
    return 'NO_VERDICT'


def run(path: Path, timeout: int) -> dict:
    started = time.time()
    try:
        result = subprocess.run(['tau', '-X', '-q', '-c', 'false'], input=path.read_text(),
                                capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        return {'file': path.name, 'obtained': classify(output),
                'returncode': result.returncode,
                'wall_s': round(time.time() - started, 3)}
    except subprocess.TimeoutExpired:
        return {'file': path.name, 'obtained': 'TIMEOUT', 'returncode': 124,
                'wall_s': round(time.time() - started, 3)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', type=Path, default=Path('tau/agent_transition.tau'))
    parser.add_argument('--mutation', type=Path, default=Path('tau/agent_transition_mutation.tau'))
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--output', type=Path, default=Path('tau/verdict.json'))
    args = parser.parse_args()
    cases = [run(args.kernel, args.timeout), run(args.mutation, args.timeout)]
    cases[0]['expected'] = 'SAT'
    cases[1]['expected'] = 'UNSAT'
    for case in cases:
        case['status'] = 'PASS' if case['obtained'] == case['expected'] else 'FAIL'
    report = {'status': 'PASS' if all(c['status'] == 'PASS' for c in cases) else 'FAIL',
              'cases': cases, 'command': 'tau -X -q -c false < spec.tau'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
