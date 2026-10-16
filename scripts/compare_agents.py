#!/usr/bin/env python3
"""Compare plusieurs agents sur la même mission et les mêmes fixtures."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from llm_harness import validate_trace
from llm_replay import replay_trace

ROOT = Path(__file__).resolve().parents[1]


def summarize_comparison(records: list[dict]) -> dict:
    passed = sum(r.get('status') == 'PASS' for r in records)
    return {'agents': len(records), 'pass': passed, 'fail': len(records) - passed,
            'all_pass': bool(records) and passed == len(records)}


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_tau() -> bool:
    command = [sys.executable, str(ROOT / 'scripts' / 'run_tau_gate.py')]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1]).get('status') == 'PASS'
    except (IndexError, json.JSONDecodeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, default=Path('agent_comparison.json'))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    records = []
    for item in manifest['agents']:
        events = load_events(Path(item['trace']))
        fixtures = json.loads(Path(item['fixtures']).read_text())
        trace = validate_trace(events, set(item.get('allow_tools', [])))
        replay = replay_trace(events, fixtures)
        records.append({'agent': item['agent'], 'trace': trace, 'replay': replay,
                        'status': 'PASS' if trace['valid'] and replay['replayed'] else 'FAIL'})
    tau_ok = run_tau() if summarize_comparison(records)['all_pass'] else False
    report = {'status': 'PASS' if summarize_comparison(records)['all_pass'] and tau_ok else 'FAIL',
              'agents': records, 'tau': 'PASS' if tau_ok else 'FAIL',
              'summary': summarize_comparison(records)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'summary': report['summary'],
                      'output': str(args.output)}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
