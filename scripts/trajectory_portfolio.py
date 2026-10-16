#!/usr/bin/env python3
"""Lot de trajectoires distinctes. Le harness peut les accepter toutes ; Tau non."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_harness import validate_trace
from run_tau_gate import run_emitted

ROOT = Path(__file__).resolve().parents[1]


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_portfolio(manifest: Path) -> list[dict]:
    data = json.loads(manifest.read_text())
    root = manifest.parent if manifest.parent.name != 'docs' else manifest.parents[1]
    if not (root / 'docs').is_dir():
        root = ROOT
    rows = []
    for item in data['traces']:
        events = load_events(root / item['path'])
        rows.append({
            'name': item['name'],
            'path': item['path'],
            'events': events,
            'shape': tuple(event.get('type') for event in events),
            'harness_expected': item['harness'],
            'kernel_expected': item['kernel'],
            'allow_tools': set(data.get('allow_tools', [])),
        })
    return rows


def summarize_portfolio(rows: list[dict]) -> dict:
    matched = sum(
        row.get('kernel_obtained') == row.get('kernel_expected')
        and row.get('harness_obtained') == row.get('harness_expected')
        for row in rows
    )
    shapes = {row.get('shape') for row in rows}
    kernels = {row.get('kernel_expected') for row in rows}
    legal = sum(row.get('kernel_expected') == 'SAT' for row in rows)
    illegal = sum(row.get('kernel_expected') == 'UNSAT' for row in rows)
    ok = bool(rows) and matched == len(rows) and len(shapes) >= 3 and legal >= 1 and illegal >= 1
    return {
        'traces': len(rows),
        'shapes': len(shapes),
        'legal': legal,
        'illegal': illegal,
        'matched': matched,
        'kernels': sorted(kernels),
        'status': 'PASS' if ok else 'FAIL',
    }


def run_portfolio(manifest: Path, output: Path) -> dict:
    rows = []
    for item in load_portfolio(manifest):
        harness = validate_trace(item['events'], item['allow_tools'])
        tau = run_emitted(ROOT / item['path'], timeout=60)
        kernel = next(case for case in tau['cases'] if case['case'] == 'kernel')
        rows.append({
            'name': item['name'],
            'shape': ''.join(kind[0] for kind in item['shape'] if isinstance(kind, str)),
            'events': len(item['events']),
            'harness_expected': item['harness_expected'],
            'harness_obtained': harness['status'],
            'kernel_expected': item['kernel_expected'],
            'kernel_obtained': kernel['obtained'],
            'gate': tau['status'],
            'wall_s': round(sum(case['wall_s'] for case in tau['cases']), 3),
        })
    summary = summarize_portfolio(rows)
    report = {**summary, 'rows': rows, 'command': 'tau -X -q -c false < spec.tau'}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'docs' / 'trajectory_portfolio.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'trajectory_portfolio.json')
    args = parser.parse_args()
    report = run_portfolio(args.manifest, args.output)
    print(json.dumps({'status': report['status'], 'traces': report['traces'],
                      'shapes': report['shapes'], 'matched': report['matched'],
                      'output': str(args.output)}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
