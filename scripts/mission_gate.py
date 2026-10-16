#!/usr/bin/env python3
"""Porte de mission : trace canonique, replay déterministe, puis Tau."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

from llm_harness import validate_trace
from llm_replay import replay_trace

ROOT = Path(__file__).resolve().parents[1]


def summarize_mission(trace_ok: bool, replay_ok: bool, tau_ok: bool) -> dict:
    if not trace_ok:
        return {'status': 'FAIL', 'blocked_by': 'trace'}
    if not replay_ok:
        return {'status': 'FAIL', 'blocked_by': 'replay'}
    if not tau_ok:
        return {'status': 'FAIL', 'blocked_by': 'tau'}
    return {'status': 'PASS', 'blocked_by': None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('--allow-tool', action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('mission_verdict.json'))
    args = parser.parse_args()
    events = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    fixtures = json.loads(args.fixtures.read_text())
    trace = validate_trace(events, set(args.allow_tool))
    replay = replay_trace(events, fixtures)
    tau = {'status': 'NOT_RUN'}
    if trace['valid'] and replay['replayed']:
        command = [sys.executable, str(ROOT / 'scripts' / 'run_tau_gate.py')]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        try:
            tau = json.loads(run.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            tau = {'status': 'FAIL', 'stderr': run.stderr[-1000:]}
    report = {'status': summarize_mission(trace['valid'], replay['replayed'], tau['status'] == 'PASS')['status'],
              'trace': trace, 'replay': replay, 'tau': tau}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(args.output)}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
