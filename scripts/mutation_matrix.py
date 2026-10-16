#!/usr/bin/env python3
"""Matrice nominale + mutations : toutes les trajectoires interdites doivent échouer."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from llm_harness import validate_trace
from llm_mutations import MUTATIONS, mutate_trace
from llm_replay import replay_trace


def summarize_matrix(nominal_ok: bool, mutation_validities: list[bool]) -> dict:
    rejected = sum(not valid for valid in mutation_validities)
    return {'nominal': 'PASS' if nominal_ok else 'FAIL',
            'mutations': len(mutation_validities), 'rejected': rejected,
            'status': 'PASS' if nominal_ok and rejected == len(mutation_validities) else 'FAIL'}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('--allow-tool', action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('mutation_matrix.json'))
    args = parser.parse_args()
    events = load(args.trace)
    fixtures = json.loads(args.fixtures.read_text())
    tools = set(args.allow_tool)
    nominal_trace = validate_trace(events, tools)
    nominal_replay = replay_trace(events, fixtures)
    nominal_ok = nominal_trace['valid'] and nominal_replay['replayed']
    mutations = []
    for name in MUTATIONS:
        mutated = mutate_trace(events, name)
        trace = validate_trace(mutated, tools)
        replay = replay_trace(mutated, fixtures)
        valid = trace['valid'] and replay['replayed']
        mutations.append({'mutation': name, 'accepted': valid,
                          'trace': trace, 'replay': replay})
    summary = summarize_matrix(nominal_ok, [m['accepted'] for m in mutations])
    report = {'status': summary['status'], 'summary': summary,
              'nominal': {'trace': nominal_trace, 'replay': nominal_replay},
              'mutations': mutations}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'summary': summary,
                      'output': str(args.output)}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
